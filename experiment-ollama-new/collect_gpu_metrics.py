#!/usr/bin/env python3

"""Collect the DCGM time series required by the Ollama experiment."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


METRICS = (
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE",
    "DCGM_FI_PROF_DRAM_ACTIVE",
    "DCGM_FI_DEV_FB_USED",
    "DCGM_FI_DEV_FB_FREE",
    "DCGM_FI_DEV_POWER_USAGE",
)


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
            prometheus_url,
            "/api/v1/query",
            {"query": metric},
            timeout_seconds,
        )
        result = payload.get("data", {}).get("result", [])
        series_counts[metric] = len(result)
        if not result:
            missing.append(metric)

    if missing:
        raise PrometheusError(
            "no current series returned for: " + ", ".join(missing)
        )

    details = ", ".join(
        f"{metric}={series_counts[metric]}" for metric in METRICS
    )
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


def collect_metrics(
    prometheus_url: str,
    workload_start: float,
    workload_end: float,
    step_seconds: float,
    padding_before_seconds: float,
    padding_after_seconds: float,
    timeout_seconds: float,
    output: Path,
) -> None:
    if workload_end <= workload_start:
        raise ValueError("workload end must be greater than workload start")
    if step_seconds <= 0:
        raise ValueError("step must be greater than zero")

    query_start = workload_start - padding_before_seconds
    query_end = workload_end + padding_after_seconds
    collected_metrics: dict[str, dict] = {}
    missing: list[str] = []

    for metric in METRICS:
        payload = prometheus_get(
            prometheus_url,
            "/api/v1/query_range",
            {
                "query": metric,
                "start": query_start,
                "end": query_end,
                "step": step_seconds,
            },
            timeout_seconds,
        )
        data = payload.get("data", {})
        series = data.get("result", [])
        if not series:
            missing.append(metric)
        collected_metrics[metric] = {
            "query": metric,
            "result_type": data.get("resultType"),
            "series": series,
        }

    if missing:
        raise PrometheusError(
            "no range data returned for: " + ", ".join(missing)
        )

    document = {
        "schema_version": 1,
        "collected_at_utc": utc_now(),
        "prometheus_url": prometheus_url,
        "workload_window": {
            "start_unix_s": workload_start,
            "end_unix_s": workload_end,
            "duration_seconds": workload_end - workload_start,
        },
        "query_window": {
            "start_unix_s": query_start,
            "end_unix_s": query_end,
            "padding_before_seconds": padding_before_seconds,
            "padding_after_seconds": padding_after_seconds,
            "step_seconds": step_seconds,
        },
        "metrics": collected_metrics,
    }
    write_json_atomic(output, document)

    total_series = sum(
        len(metric_document["series"])
        for metric_document in collected_metrics.values()
    )
    print(
        f"Saved {len(collected_metrics)} metrics / {total_series} series "
        f"to {output}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prometheus-url",
        default="http://10.146.0.55:30090",
        help="Prometheus base URL",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="verify that every required metric is available")

    collect_parser = subparsers.add_parser(
        "collect", help="collect range data for one workload window"
    )
    collect_parser.add_argument("--start", type=float, required=True)
    collect_parser.add_argument("--end", type=float, required=True)
    collect_parser.add_argument("--step", type=float, default=5.0)
    collect_parser.add_argument("--padding-before", type=float, default=15.0)
    collect_parser.add_argument("--padding-after", type=float, default=5.0)
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
                step_seconds=args.step,
                padding_before_seconds=args.padding_before,
                padding_after_seconds=args.padding_after,
                timeout_seconds=args.timeout,
                output=args.output,
            )
    except (PrometheusError, ValueError) as exc:
        print(f"GPU metrics collection failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
