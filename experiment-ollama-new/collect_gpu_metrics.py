#!/usr/bin/env python3

"""Collect delayed DCGM samples for one Ollama workload.

DCGM is exported every five seconds in this testbed. A short workload can
therefore finish before the first non-idle sample is scraped by Prometheus.
This collector reads raw samples with a PromQL range vector and waits until the
delayed SM-activity episode has appeared and returned to idle.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


METRICS = (
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE",
    "DCGM_FI_PROF_DRAM_ACTIVE",
    "DCGM_FI_DEV_FB_USED",
    "DCGM_FI_DEV_FB_FREE",
    "DCGM_FI_DEV_POWER_USAGE",
)
ACTIVITY_METRIC = "DCGM_FI_PROF_GR_ENGINE_ACTIVE"


class PrometheusError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def prometheus_get(
    prometheus_url: str,
    endpoint: str,
    params: dict[str, str | float],
    timeout_seconds: float,
) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{prometheus_url.rstrip('/')}{endpoint}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PrometheusError(f"request failed for {endpoint}: {exc}") from exc

    if payload.get("status") != "success":
        error_type = payload.get("errorType", "unknown")
        error = payload.get("error", "Prometheus returned a non-success response")
        raise PrometheusError(f"{error_type}: {error}")
    return payload


def check_metrics(prometheus_url: str, timeout_seconds: float) -> None:
    missing: list[str] = []
    series_counts: dict[str, int] = {}
    for metric in METRICS:
        payload = prometheus_get(
            prometheus_url, "/api/v1/query", {"query": metric}, timeout_seconds
        )
        result = payload.get("data", {}).get("result", [])
        series_counts[metric] = len(result)
        if not result:
            missing.append(metric)

    if missing:
        raise PrometheusError("no current series returned for: " + ", ".join(missing))
    details = ", ".join(f"{metric}={series_counts[metric]}" for metric in METRICS)
    print(f"Prometheus preflight OK ({details})")


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        json.dump(payload, temporary_file, indent=2, sort_keys=True)
        temporary_file.write("\n")
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(path)


def raw_range_query(
    prometheus_url: str,
    metric: str,
    query_start: float,
    query_end: float,
    timeout_seconds: float,
) -> dict:
    """Return stored samples rather than query_range evaluation points."""
    range_seconds = max(1, int(math.ceil(query_end - query_start)) + 1)
    payload = prometheus_get(
        prometheus_url,
        "/api/v1/query",
        {"query": f"{metric}[{range_seconds}s]", "time": query_end},
        timeout_seconds,
    )
    data = payload.get("data", {})
    filtered_series: list[dict] = []
    for item in data.get("result", []):
        values = [
            value
            for value in item.get("values", [])
            if query_start <= float(value[0]) <= query_end
        ]
        if values:
            filtered_series.append({"metric": item.get("metric", {}), "values": values})
    return {
        "query": f"{metric}[{range_seconds}s]",
        "result_type": data.get("resultType"),
        "series": filtered_series,
    }


def activity_state(
    series: list[dict],
    workload_start: float,
    threshold_fraction: float,
    settle_samples: int,
) -> tuple[bool, bool, int, int]:
    """Return observed, settled, active-timestamp count, trailing-idle count."""
    by_timestamp: dict[float, list[float]] = defaultdict(list)
    for item in series:
        for timestamp_raw, value_raw in item.get("values", []):
            timestamp = float(timestamp_raw)
            if timestamp >= workload_start:
                by_timestamp[timestamp].append(float(value_raw))

    states = [
        (timestamp, max(values) > threshold_fraction)
        for timestamp, values in sorted(by_timestamp.items())
        if values
    ]
    active_positions = [index for index, (_, active) in enumerate(states) if active]
    if not active_positions:
        return False, False, 0, 0

    last_active = active_positions[-1]
    trailing_idle = sum(1 for _, active in states[last_active + 1 :] if not active)
    return True, trailing_idle >= settle_samples, len(active_positions), trailing_idle


def collect_metrics(
    prometheus_url: str,
    workload_start: float,
    workload_end: float,
    nominal_sample_interval_seconds: float,
    padding_before_seconds: float,
    wait_timeout_seconds: float,
    poll_seconds: float,
    settle_samples: int,
    activity_threshold_pct: float,
    timeout_seconds: float,
    output: Path,
) -> None:
    if workload_end <= workload_start:
        raise ValueError("workload end must be greater than workload start")
    if nominal_sample_interval_seconds <= 0:
        raise ValueError("nominal sample interval must be greater than zero")
    if padding_before_seconds < nominal_sample_interval_seconds:
        raise ValueError("padding before must be at least one nominal sample interval")
    if wait_timeout_seconds < 0 or poll_seconds <= 0:
        raise ValueError("wait timeout must be non-negative and poll interval positive")
    if settle_samples < 1:
        raise ValueError("settle samples must be at least one")
    if activity_threshold_pct < 0:
        raise ValueError("activity threshold must be non-negative")

    query_start = workload_start - padding_before_seconds
    threshold_fraction = activity_threshold_pct / 100.0
    wait_started = time.time()
    deadline = wait_started + wait_timeout_seconds
    observed = False
    settled = False
    active_sample_count = 0
    trailing_idle_samples = 0

    while True:
        query_end = time.time()
        activity_document = raw_range_query(
            prometheus_url, ACTIVITY_METRIC, query_start, query_end, timeout_seconds
        )
        observed, settled, active_sample_count, trailing_idle_samples = activity_state(
            activity_document["series"],
            workload_start,
            threshold_fraction,
            settle_samples,
        )
        if observed and settled:
            break
        if query_end >= deadline:
            break
        state = "waiting for return to idle" if observed else "waiting for delayed activity"
        print(f"GPU telemetry: {state} ...", flush=True)
        time.sleep(min(poll_seconds, max(0.0, deadline - query_end)))

    collection_end = time.time()
    collected_metrics: dict[str, dict] = {}
    missing: list[str] = []
    for metric in METRICS:
        metric_document = raw_range_query(
            prometheus_url, metric, query_start, collection_end, timeout_seconds
        )
        if not metric_document["series"]:
            missing.append(metric)
        collected_metrics[metric] = metric_document

    if missing:
        raise PrometheusError("no raw range data returned for: " + ", ".join(missing))

    wait_status = (
        "settled"
        if settled
        else ("activity_not_settled" if observed else "activity_not_observed")
    )
    document = {
        "schema_version": 2,
        "collected_at_utc": utc_now(),
        "prometheus_url": prometheus_url,
        "workload_window": {
            "start_unix_s": workload_start,
            "end_unix_s": workload_end,
            "duration_seconds": workload_end - workload_start,
        },
        "query_window": {
            "start_unix_s": query_start,
            "end_unix_s": collection_end,
            "padding_before_seconds": padding_before_seconds,
            "padding_after_seconds": collection_end - workload_end,
            "step_seconds": nominal_sample_interval_seconds,
            "sample_source": "raw Prometheus samples via instant range-vector query",
        },
        "activity_capture": {
            "metric": ACTIVITY_METRIC,
            "threshold_pct_per_partition": activity_threshold_pct,
            "settle_samples_required": settle_samples,
            "active_sample_count": active_sample_count,
            "trailing_idle_samples": trailing_idle_samples,
            "status": wait_status,
            "wait_seconds": collection_end - wait_started,
            "wait_timeout_seconds": wait_timeout_seconds,
            "poll_seconds": poll_seconds,
        },
        "metrics": collected_metrics,
    }
    write_json_atomic(output, document)

    total_series = sum(len(item["series"]) for item in collected_metrics.values())
    print(
        f"Saved {len(collected_metrics)} metrics / {total_series} series to {output} "
        f"(activity capture: {wait_status}, wait {collection_end - wait_started:.1f}s)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prometheus-url", default="http://10.146.0.55:30090", help="Prometheus base URL"
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="verify that every required metric is available")

    collect_parser = subparsers.add_parser(
        "collect", help="wait for and collect the delayed GPU activity episode"
    )
    collect_parser.add_argument("--start", type=float, required=True)
    collect_parser.add_argument("--end", type=float, required=True)
    collect_parser.add_argument("--sample-interval", type=float, default=5.0)
    collect_parser.add_argument("--padding-before", type=float, default=20.0)
    collect_parser.add_argument("--wait-timeout", type=float, default=25.0)
    collect_parser.add_argument("--poll-seconds", type=float, default=2.0)
    collect_parser.add_argument("--settle-samples", type=int, default=1)
    collect_parser.add_argument("--activity-threshold-pct", type=float, default=0.1)
    collect_parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "check":
            check_metrics(args.prometheus_url, args.timeout)
        else:
            collect_metrics(
                prometheus_url=args.prometheus_url,
                workload_start=args.start,
                workload_end=args.end,
                nominal_sample_interval_seconds=args.sample_interval,
                padding_before_seconds=args.padding_before,
                wait_timeout_seconds=args.wait_timeout,
                poll_seconds=args.poll_seconds,
                settle_samples=args.settle_samples,
                activity_threshold_pct=args.activity_threshold_pct,
                timeout_seconds=args.timeout,
                output=args.output,
            )
    except (PrometheusError, ValueError) as exc:
        print(f"GPU metrics collection failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
