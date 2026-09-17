#!/usr/bin/env python3

from __future__ import annotations

import bisect
import csv
import json
import math
import os
import re
import shutil
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
REQUESTS_FILE = RESULTS_DIR / "results.jsonl"
METADATA_FILE = RESULTS_DIR / "metadata.json"
TABLE_FILE = RESULTS_DIR / "results_table.csv"
GPU_METRICS_FILE = Path(
    os.environ.get("GPU_METRICS_FILE", str(RESULTS_DIR / "gpu-metrics.json"))
)
GPU_CSV_FILE = RESULTS_DIR / "gpu-metrics.csv"
RUN_SUMMARY_FILE = RESULTS_DIR / "run-summary.json"

TOTAL_MIG_COMPUTE_SLICES = float(os.environ.get("MIG_TOTAL_COMPUTE_SLICES", "7"))
PHYSICAL_MEMORY_OVERRIDE_MIB = os.environ.get("GPU_PHYSICAL_MEMORY_MIB")

METRIC_FIELDS = {
    "DCGM_FI_PROF_GR_ENGINE_ACTIVE": "sm_active_fraction",
    "DCGM_FI_PROF_DRAM_ACTIVE": "dram_active_fraction",
    "DCGM_FI_DEV_FB_USED": "fb_used_mib",
    "DCGM_FI_DEV_FB_FREE": "fb_free_mib",
}
POWER_METRIC = "DCGM_FI_DEV_POWER_USAGE"


def env_flag_is_enabled(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


WRITE_RUN_TO_TABLE = env_flag_is_enabled(os.environ.get("SAVE_RESULT_LOG"))
RESULT_LOG = os.environ.get("RESULT_LOG")
RUN_RESULT_BASE = os.environ.get("RUN_RESULT_BASE")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean_or_none(values: Iterable[float]) -> float | None:
    values = list(values)
    return statistics.fmean(values) if values else None


def round_or_blank(value: float | None, digits: int = 3) -> float | str:
    return "" if value is None else round(value, digits)


def load_records() -> list[dict]:
    records: list[dict] = []
    with REQUESTS_FILE.open(encoding="utf-8") as request_file:
        for line_number, line in enumerate(request_file, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON in {REQUESTS_FILE} at line {line_number}: {exc}"
                ) from exc

    if not records:
        raise ValueError(f"no request records found in {REQUESTS_FILE}")
    return records


def load_metadata() -> dict:
    if not METADATA_FILE.exists():
        return {}
    with METADATA_FILE.open(encoding="utf-8") as metadata_file:
        return json.load(metadata_file)


def format_created_time(created_at: str) -> str:
    time_part = created_at.split("T", 1)[1].rstrip("Z")
    if "." not in time_part:
        return f"{time_part}.00"

    hms, fraction = time_part.split(".", 1)
    hundredths = fraction[:2].ljust(2, "0")
    return f"{hms}.{hundredths}"


def active_request_count(records: list[dict], timestamp: float) -> int:
    timestamp_ms = timestamp * 1000.0
    return sum(
        1
        for record in records
        if float(record["start_time"]) <= timestamp_ms <= float(record["end_time"])
    )


def physical_gpu_key(labels: dict) -> str:
    return str(
        labels.get("UUID")
        or labels.get("pci_bus_id")
        or labels.get("device")
        or labels.get("gpu")
        or "unknown-gpu"
    )


def profile_compute_slices(profile: str | None) -> float:
    if not profile:
        return TOTAL_MIG_COMPUTE_SLICES
    match = re.match(r"^(\d+)g\.", profile)
    return float(match.group(1)) if match else TOTAL_MIG_COMPUTE_SLICES


def profile_memory_gib(profile: str | None, physical_memory_gib: float) -> float:
    if not profile:
        return physical_memory_gib
    match = re.search(r"\.(\d+)gb", profile, flags=re.IGNORECASE)
    return float(match.group(1)) if match else physical_memory_gib


def physical_memory_mib(labels: dict) -> float | None:
    if PHYSICAL_MEMORY_OVERRIDE_MIB:
        return finite_float(PHYSICAL_MEMORY_OVERRIDE_MIB)

    model_name = str(labels.get("modelName", ""))
    match = re.search(r"(\d+)\s*GB", model_name, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1)) * 1024.0


def average_nested(values: dict[float, list[float]], timestamp: float) -> float | None:
    return mean_or_none(values.get(timestamp, []))


def build_gpu_rows(raw_document: dict, records: list[dict]) -> dict[str, list[dict]]:
    partition_values: dict[tuple[str, str, str], dict[str, dict[float, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    partition_labels: dict[tuple[str, str, str], dict] = {}
    power_values: dict[str, dict[float, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    gpu_labels: dict[str, dict] = {}

    metrics_document = raw_document.get("metrics", {})
    for metric_name, field_name in METRIC_FIELDS.items():
        metric_document = metrics_document.get(metric_name, {})
        for series in metric_document.get("series", []):
            labels = series.get("metric", {})
            gpu_key = physical_gpu_key(labels)
            gpu_instance_id = str(labels.get("GPU_I_ID", "full"))
            profile = str(labels.get("GPU_I_PROFILE", "full"))
            partition_key = (gpu_key, gpu_instance_id, profile)
            partition_labels[partition_key] = labels
            gpu_labels.setdefault(gpu_key, labels)

            for timestamp_raw, value_raw in series.get("values", []):
                timestamp = finite_float(timestamp_raw)
                value = finite_float(value_raw)
                if timestamp is None or value is None:
                    continue
                partition_values[partition_key][field_name][timestamp].append(value)

    power_document = metrics_document.get(POWER_METRIC, {})
    for series in power_document.get("series", []):
        labels = series.get("metric", {})
        gpu_key = physical_gpu_key(labels)
        gpu_labels.setdefault(gpu_key, labels)
        for timestamp_raw, value_raw in series.get("values", []):
            timestamp = finite_float(timestamp_raw)
            value = finite_float(value_raw)
            if timestamp is None or value is None:
                continue
            # DCGM exposes board power once per MIG instance. These values describe
            # the same physical GPU and must be averaged, never summed.
            power_values[gpu_key][timestamp].append(value)

    partition_rows: list[dict] = []
    partition_rows_by_gpu_time: dict[tuple[str, float], list[dict]] = defaultdict(list)

    for partition_key, fields in partition_values.items():
        gpu_key, gpu_instance_id, profile = partition_key
        labels = partition_labels[partition_key]
        timestamps = sorted(
            {timestamp for values in fields.values() for timestamp in values}
        )

        for timestamp in timestamps:
            sm_fraction = average_nested(fields["sm_active_fraction"], timestamp)
            dram_fraction = average_nested(fields["dram_active_fraction"], timestamp)
            fb_used = average_nested(fields["fb_used_mib"], timestamp)
            fb_free = average_nested(fields["fb_free_mib"], timestamp)
            fb_total = (
                fb_used + fb_free
                if fb_used is not None and fb_free is not None
                else None
            )
            fb_util = (
                100.0 * fb_used / fb_total
                if fb_used is not None and fb_total and fb_total > 0
                else None
            )
            row = {
                "timestamp_unix_s": timestamp,
                "scope": "partition",
                "gpu_uuid": gpu_key,
                "gpu": labels.get("gpu"),
                "gpu_i_id": gpu_instance_id,
                "gpu_i_profile": profile,
                "model_name": labels.get("modelName"),
                "active_requests": active_request_count(records, timestamp),
                "sm_partition_pct": None if sm_fraction is None else 100.0 * sm_fraction,
                "sm_configured_pct": None,
                "sm_physical_pct": None,
                "dram_partition_pct": None if dram_fraction is None else 100.0 * dram_fraction,
                "dram_configured_pct": None,
                "dram_physical_pct": None,
                "fb_used_mib": fb_used,
                "fb_free_mib": fb_free,
                "fb_util_partition_pct": fb_util,
                "fb_util_configured_pct": None,
                "fb_util_physical_pct": None,
                "configured_compute_pct": None,
                "configured_memory_pct": None,
                "physical_memory_mib": physical_memory_mib(labels),
                "power_w": None,
            }
            partition_rows.append(row)
            partition_rows_by_gpu_time[(gpu_key, timestamp)].append(row)

    physical_rows: list[dict] = []
    gpu_keys = sorted(set(gpu_labels) | set(power_values))
    for gpu_key in gpu_keys:
        timestamps = sorted(
            {timestamp for key, timestamp in partition_rows_by_gpu_time if key == gpu_key}
            | set(power_values[gpu_key])
        )
        labels = gpu_labels.get(gpu_key, {})
        gpu_memory_mib = physical_memory_mib(labels)
        gpu_memory_gib = gpu_memory_mib / 1024.0 if gpu_memory_mib else 0.0

        for timestamp in timestamps:
            partitions = partition_rows_by_gpu_time.get((gpu_key, timestamp), [])

            sm_weighted_sum = 0.0
            sm_weight_sum = 0.0
            dram_weighted_sum = 0.0
            dram_weight_sum = 0.0
            configured_compute_slices = 0.0
            configured_memory_gib = 0.0

            fb_used_values: list[float] = []
            fb_free_values: list[float] = []
            for partition in partitions:
                compute_weight = profile_compute_slices(partition["gpu_i_profile"])
                memory_weight = profile_memory_gib(
                    partition["gpu_i_profile"], gpu_memory_gib
                )
                configured_compute_slices += compute_weight
                configured_memory_gib += memory_weight

                if partition["sm_partition_pct"] is not None:
                    sm_weighted_sum += partition["sm_partition_pct"] * compute_weight
                    sm_weight_sum += compute_weight
                if partition["dram_partition_pct"] is not None:
                    dram_weighted_sum += partition["dram_partition_pct"] * memory_weight
                    dram_weight_sum += memory_weight
                if partition["fb_used_mib"] is not None:
                    fb_used_values.append(partition["fb_used_mib"])
                if partition["fb_free_mib"] is not None:
                    fb_free_values.append(partition["fb_free_mib"])

            fb_used = sum(fb_used_values) if fb_used_values else None
            fb_free = sum(fb_free_values) if fb_free_values else None
            configured_fb = (
                fb_used + fb_free
                if fb_used is not None and fb_free is not None
                else None
            )
            sm_configured = (
                sm_weighted_sum / sm_weight_sum if sm_weight_sum > 0 else None
            )
            sm_physical = (
                sm_weighted_sum / TOTAL_MIG_COMPUTE_SLICES
                if sm_weight_sum > 0
                else None
            )
            dram_configured = (
                dram_weighted_sum / dram_weight_sum if dram_weight_sum > 0 else None
            )
            dram_physical = (
                dram_weighted_sum / gpu_memory_gib
                if dram_weight_sum > 0 and gpu_memory_gib > 0
                else None
            )

            physical_rows.append(
                {
                    "timestamp_unix_s": timestamp,
                    "scope": "physical_gpu",
                    "gpu_uuid": gpu_key,
                    "gpu": labels.get("gpu"),
                    "gpu_i_id": None,
                    "gpu_i_profile": None,
                    "model_name": labels.get("modelName"),
                    "active_requests": active_request_count(records, timestamp),
                    "sm_partition_pct": None,
                    "sm_configured_pct": sm_configured,
                    "sm_physical_pct": sm_physical,
                    "dram_partition_pct": None,
                    "dram_configured_pct": dram_configured,
                    "dram_physical_pct": dram_physical,
                    "fb_used_mib": fb_used,
                    "fb_free_mib": fb_free,
                    "fb_util_partition_pct": None,
                    "fb_util_configured_pct": (
                        100.0 * fb_used / configured_fb
                        if fb_used is not None and configured_fb and configured_fb > 0
                        else None
                    ),
                    "fb_util_physical_pct": (
                        100.0 * fb_used / gpu_memory_mib
                        if fb_used is not None and gpu_memory_mib and gpu_memory_mib > 0
                        else None
                    ),
                    "configured_compute_pct": (
                        100.0
                        * min(configured_compute_slices, TOTAL_MIG_COMPUTE_SLICES)
                        / TOTAL_MIG_COMPUTE_SLICES
                        if partitions
                        else None
                    ),
                    "configured_memory_pct": (
                        100.0 * configured_fb / gpu_memory_mib
                        if configured_fb is not None
                        and gpu_memory_mib
                        and gpu_memory_mib > 0
                        else None
                    ),
                    "physical_memory_mib": gpu_memory_mib,
                    "power_w": mean_or_none(power_values[gpu_key].get(timestamp, [])),
                }
            )

    physical_rows_by_time: dict[float, list[dict]] = defaultdict(list)
    for row in physical_rows:
        physical_rows_by_time[row["timestamp_unix_s"]].append(row)

    system_rows: list[dict] = []
    for timestamp, rows in sorted(physical_rows_by_time.items()):
        fb_used_values = [row["fb_used_mib"] for row in rows if row["fb_used_mib"] is not None]
        fb_free_values = [row["fb_free_mib"] for row in rows if row["fb_free_mib"] is not None]
        physical_memory_values = [
            row["physical_memory_mib"]
            for row in rows
            if row["physical_memory_mib"] is not None
        ]
        total_fb_used = sum(fb_used_values) if fb_used_values else None
        total_fb_free = sum(fb_free_values) if fb_free_values else None
        configured_fb = (
            total_fb_used + total_fb_free
            if total_fb_used is not None and total_fb_free is not None
            else None
        )
        total_physical_memory = (
            sum(physical_memory_values) if physical_memory_values else None
        )
        power_values_at_timestamp = [
            row["power_w"] for row in rows if row["power_w"] is not None
        ]

        system_rows.append(
            {
                "timestamp_unix_s": timestamp,
                "scope": "system",
                "gpu_uuid": "all",
                "gpu": None,
                "gpu_i_id": None,
                "gpu_i_profile": None,
                "model_name": None,
                "active_requests": active_request_count(records, timestamp),
                "sm_partition_pct": None,
                "sm_configured_pct": mean_or_none(
                    row["sm_configured_pct"]
                    for row in rows
                    if row["sm_configured_pct"] is not None
                ),
                "sm_physical_pct": mean_or_none(
                    row["sm_physical_pct"]
                    for row in rows
                    if row["sm_physical_pct"] is not None
                ),
                "dram_partition_pct": None,
                "dram_configured_pct": mean_or_none(
                    row["dram_configured_pct"]
                    for row in rows
                    if row["dram_configured_pct"] is not None
                ),
                "dram_physical_pct": mean_or_none(
                    row["dram_physical_pct"]
                    for row in rows
                    if row["dram_physical_pct"] is not None
                ),
                "fb_used_mib": total_fb_used,
                "fb_free_mib": total_fb_free,
                "fb_util_partition_pct": None,
                "fb_util_configured_pct": (
                    100.0 * total_fb_used / configured_fb
                    if total_fb_used is not None and configured_fb and configured_fb > 0
                    else None
                ),
                "fb_util_physical_pct": (
                    100.0 * total_fb_used / total_physical_memory
                    if total_fb_used is not None
                    and total_physical_memory
                    and total_physical_memory > 0
                    else None
                ),
                "configured_compute_pct": mean_or_none(
                    row["configured_compute_pct"]
                    for row in rows
                    if row["configured_compute_pct"] is not None
                ),
                "configured_memory_pct": (
                    100.0 * configured_fb / total_physical_memory
                    if configured_fb is not None
                    and total_physical_memory
                    and total_physical_memory > 0
                    else None
                ),
                "physical_memory_mib": total_physical_memory,
                "power_w": sum(power_values_at_timestamp)
                if power_values_at_timestamp
                else None,
            }
        )

    workload_start = min(float(record["start_time"]) for record in records) / 1000.0
    for row in partition_rows + physical_rows + system_rows:
        timestamp = row["timestamp_unix_s"]
        row["timestamp_utc"] = datetime.fromtimestamp(
            timestamp, timezone.utc
        ).isoformat().replace("+00:00", "Z")
        row["relative_to_test_start_s"] = timestamp - workload_start

    return {
        "partition": sorted(
            partition_rows,
            key=lambda row: (
                row["timestamp_unix_s"],
                row["gpu_uuid"],
                str(row["gpu_i_id"]),
            ),
        ),
        "physical_gpu": sorted(
            physical_rows,
            key=lambda row: (row["timestamp_unix_s"], row["gpu_uuid"]),
        ),
        "system": sorted(system_rows, key=lambda row: row["timestamp_unix_s"]),
    }


def series_points(rows: list[dict], field: str) -> list[tuple[float, float]]:
    by_timestamp: dict[float, list[float]] = defaultdict(list)
    for row in rows:
        value = finite_float(row.get(field))
        if value is not None:
            by_timestamp[float(row["timestamp_unix_s"])].append(value)
    return [
        (timestamp, statistics.fmean(values))
        for timestamp, values in sorted(by_timestamp.items())
    ]


def interpolate(points: list[tuple[float, float]], timestamp: float) -> float | None:
    if not points:
        return None
    timestamps = [point[0] for point in points]
    position = bisect.bisect_left(timestamps, timestamp)

    if position < len(points) and points[position][0] == timestamp:
        return points[position][1]
    if position == 0:
        return points[0][1]
    if position == len(points):
        return points[-1][1]

    left_time, left_value = points[position - 1]
    right_time, right_value = points[position]
    fraction = (timestamp - left_time) / (right_time - left_time)
    return left_value + fraction * (right_value - left_value)


def clip_points(
    points: list[tuple[float, float]], start: float, end: float
) -> list[tuple[float, float]]:
    if not points or end <= start:
        return []
    start_value = interpolate(points, start)
    end_value = interpolate(points, end)
    if start_value is None or end_value is None:
        return []
    clipped = [(start, start_value)]
    clipped.extend((timestamp, value) for timestamp, value in points if start < timestamp < end)
    clipped.append((end, end_value))
    return clipped


def trapezoid_integral(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    return sum(
        (right_time - left_time) * (left_value + right_value) / 2.0
        for (left_time, left_value), (right_time, right_value) in zip(
            points, points[1:]
        )
    )


def window_integral(
    points: list[tuple[float, float]], start: float, end: float
) -> float | None:
    return trapezoid_integral(clip_points(points, start, end))


def window_average(
    points: list[tuple[float, float]], start: float, end: float
) -> float | None:
    integral = window_integral(points, start, end)
    duration = end - start
    if integral is None or duration <= 0:
        return None
    return integral / duration


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * quantile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def window_sample_values(
    points: list[tuple[float, float]], start: float, end: float
) -> list[float]:
    return [value for _, value in clip_points(points, start, end)]


def pearson_correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    x_delta = [value - x_mean for value in xs]
    y_delta = [value - y_mean for value in ys]
    denominator = math.sqrt(
        sum(value * value for value in x_delta)
        * sum(value * value for value in y_delta)
    )
    if denominator == 0:
        return None
    return sum(x * y for x, y in zip(x_delta, y_delta)) / denominator


def regression_slope(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator == 0:
        return None
    return sum(
        (x - x_mean) * (y - y_mean) for x, y in pairs
    ) / denominator


def same_timestamp_pairs(
    rows: list[dict],
    first_field: str,
    second_field: str,
    start: float,
    end: float,
) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        timestamp = float(row["timestamp_unix_s"])
        first = finite_float(row.get(first_field))
        second = finite_float(row.get(second_field))
        if start <= timestamp <= end and first is not None and second is not None:
            pairs.append((first, second))
    return pairs


def median_or_none(values: Iterable[float]) -> float | None:
    values = list(values)
    return statistics.median(values) if values else None


def estimate_sample_interval(points: list[tuple[float, float]]) -> float | None:
    differences = [
        right[0] - left[0]
        for left, right in zip(points, points[1:])
        if right[0] > left[0]
    ]
    return statistics.median(differences) if differences else None


def detect_activity_episode(
    points: list[tuple[float, float]],
    workload_start: float,
    threshold_pct: float,
) -> dict | None:
    """Bound the delayed non-idle pulse with its adjacent idle samples."""
    active_positions = [
        index
        for index, (timestamp, value) in enumerate(points)
        if timestamp >= workload_start and value > threshold_pct
    ]
    if not active_positions:
        return None

    first_active = active_positions[0]
    last_active = active_positions[-1]
    start_position = max(0, first_active - 1)
    end_position = min(len(points) - 1, last_active + 1)
    return {
        "start_unix_s": points[start_position][0],
        "end_unix_s": points[end_position][0],
        "first_active_unix_s": points[first_active][0],
        "last_active_unix_s": points[last_active][0],
        "active_sample_count": len(active_positions),
        "has_leading_idle_sample": first_active > 0
        and points[first_active - 1][1] <= threshold_pct,
        "has_trailing_idle_sample": last_active + 1 < len(points)
        and points[last_active + 1][1] <= threshold_pct,
    }


def summarize_gpu_metrics(
    raw_document: dict,
    rows: dict[str, list[dict]],
    records: list[dict],
    total_tokens: int,
) -> dict:
    workload_start = min(float(record["start_time"]) for record in records) / 1000.0
    workload_end = max(float(record["end_time"]) for record in records) / 1000.0
    duration = workload_end - workload_start
    system_rows = rows["system"]

    points = {
        field: series_points(system_rows, field)
        for field in (
            "sm_configured_pct",
            "sm_physical_pct",
            "dram_configured_pct",
            "dram_physical_pct",
            "fb_used_mib",
            "fb_util_configured_pct",
            "fb_util_physical_pct",
            "configured_compute_pct",
            "configured_memory_pct",
            "power_w",
        )
    }

    activity_capture = raw_document.get("activity_capture", {})
    partition_threshold_pct = (
        finite_float(activity_capture.get("threshold_pct_per_partition")) or 0.1
    )
    physical_threshold_pct = partition_threshold_pct / TOTAL_MIG_COMPUTE_SLICES
    episode = detect_activity_episode(
        points["sm_physical_pct"], workload_start, physical_threshold_pct
    )
    sample_interval = estimate_sample_interval(points["sm_physical_pct"])
    configured_sample_interval = finite_float(
        raw_document.get("query_window", {}).get("step_seconds")
    )
    nominal_interval = sample_interval or configured_sample_interval

    episode_start = finite_float(episode.get("start_unix_s")) if episode else None
    episode_end = finite_float(episode.get("end_unix_s")) if episode else None
    episode_duration = (
        episode_end - episode_start
        if episode_start is not None
        and episode_end is not None
        and episode_end > episode_start
        else None
    )
    episode_complete = bool(
        episode
        and episode["has_leading_idle_sample"]
        and episode["has_trailing_idle_sample"]
    )

    query_window = raw_document.get("query_window", {})
    query_start = finite_float(query_window.get("start_unix_s")) or workload_start
    query_end = finite_float(query_window.get("end_unix_s")) or workload_end
    observation_start = episode_start if episode_start is not None else workload_start
    observation_end = episode_end if episode_end is not None else query_end

    sm_active_pct_seconds = (
        window_integral(points["sm_physical_pct"], episode_start, episode_end)
        if episode_start is not None and episode_end is not None
        else None
    )
    sm_configured_pct_seconds = (
        window_integral(points["sm_configured_pct"], episode_start, episode_end)
        if episode_start is not None and episode_end is not None
        else None
    )
    dram_active_pct_seconds = (
        window_integral(points["dram_physical_pct"], episode_start, episode_end)
        if episode_start is not None and episode_end is not None
        else None
    )
    dram_configured_pct_seconds = (
        window_integral(points["dram_configured_pct"], episode_start, episode_end)
        if episode_start is not None and episode_end is not None
        else None
    )

    # Samples before the delayed activity pulse are still idle observations for
    # this run, even if their timestamps fall after the HTTP workload ended.
    idle_end = episode_start if episode_start is not None else workload_start
    idle_power_samples = [
        value
        for timestamp, value in points["power_w"]
        if query_start <= timestamp < idle_end
    ]
    idle_power_w = median_or_none(idle_power_samples)

    dynamic_energy_j = None
    observed_episode_energy_j = None
    if episode_start is not None and episode_end is not None:
        observed_episode_energy_j = window_integral(
            points["power_w"], episode_start, episode_end
        )
        if idle_power_w is not None:
            dynamic_power_points = [
                (timestamp, max(0.0, value - idle_power_w))
                for timestamp, value in points["power_w"]
            ]
            dynamic_energy_j = window_integral(
                dynamic_power_points, episode_start, episode_end
            )

    # The excess-power pulse is delayed but its area remains useful. Baseline
    # energy is charged only for the actual request wall time, not for the wait.
    energy_j = (
        idle_power_w * duration + dynamic_energy_j
        if idle_power_w is not None and dynamic_energy_j is not None
        else None
    )
    energy_wh = energy_j / 3600.0 if energy_j is not None else None

    sm_samples = (
        window_sample_values(points["sm_physical_pct"], episode_start, episode_end)
        if episode_start is not None and episode_end is not None
        else []
    )
    power_samples = (
        window_sample_values(points["power_w"], episode_start, episode_end)
        if episode_start is not None and episode_end is not None
        else []
    )
    fb_used_samples = window_sample_values(
        points["fb_used_mib"], observation_start, observation_end
    )
    fb_used_mib_seconds = window_integral(
        points["fb_used_mib"], observation_start, observation_end
    )

    power_sm_pairs = (
        same_timestamp_pairs(
            system_rows,
            "sm_physical_pct",
            "power_w",
            episode_start,
            episode_end,
        )
        if episode_start is not None and episode_end is not None
        else []
    )

    unique_partitions = {
        (row["gpu_uuid"], row["gpu_i_id"], row["gpu_i_profile"])
        for row in rows["partition"]
    }
    physical_gpus = {row["gpu_uuid"] for row in rows["physical_gpu"]}
    active_sample_count = int(episode["active_sample_count"]) if episode else 0
    coarse = bool(
        nominal_interval
        and (duration < 2.0 * nominal_interval or active_sample_count < 2)
    )
    capture_status = str(activity_capture.get("status", "unknown"))
    if not episode:
        quality = "invalid_no_activity_episode"
    elif not episode_complete or capture_status == "activity_not_settled":
        quality = "incomplete_episode"
    elif coarse:
        quality = "coarse_but_comparable"
    else:
        quality = "good"

    return {
        "workload_window": {
            "start_unix_s": workload_start,
            "end_unix_s": workload_end,
            "duration_seconds": duration,
        },
        "telemetry_episode": {
            "detected": episode is not None,
            "complete": episode_complete,
            "capture_status": capture_status,
            "quality": quality,
            "start_unix_s": episode_start,
            "end_unix_s": episode_end,
            "duration_seconds": episode_duration,
            "first_active_delay_from_workload_start_s": (
                episode["first_active_unix_s"] - workload_start if episode else None
            ),
            "active_sample_count": active_sample_count,
            "physical_activity_threshold_pct": physical_threshold_pct,
            "pointwise_alignment_supported": False,
        },
        "sampling": {
            "prometheus_step_seconds": configured_sample_interval,
            "observed_median_interval_seconds": sample_interval,
            "raw_samples_used": raw_document.get("schema_version") == 2,
            "system_samples_in_episode": sum(
                1
                for row in system_rows
                if episode_start is not None
                and episode_end is not None
                and episode_start <= row["timestamp_unix_s"] <= episode_end
            ),
            "partition_count": len(unique_partitions),
            "physical_gpu_count": len(physical_gpus),
        },
        "sm_activity": {
            "configured_capacity_avg_pct": (
                sm_configured_pct_seconds / duration
                if sm_configured_pct_seconds is not None and duration > 0
                else None
            ),
            "physical_gpu_avg_pct": (
                sm_active_pct_seconds / duration
                if sm_active_pct_seconds is not None and duration > 0
                else None
            ),
            "observed_episode_physical_avg_pct": (
                sm_active_pct_seconds / episode_duration
                if sm_active_pct_seconds is not None and episode_duration
                else None
            ),
            "physical_gpu_p95_pct": percentile(sm_samples, 0.95),
            "physical_gpu_peak_pct": max(sm_samples) if sm_samples else None,
            "capacity_equivalent_active_seconds": (
                sm_active_pct_seconds / 100.0
                if sm_active_pct_seconds is not None
                else None
            ),
        },
        "dram_activity": {
            "configured_capacity_avg_pct": (
                dram_configured_pct_seconds / duration
                if dram_configured_pct_seconds is not None and duration > 0
                else None
            ),
            "physical_gpu_avg_pct": (
                dram_active_pct_seconds / duration
                if dram_active_pct_seconds is not None and duration > 0
                else None
            ),
            "observed_episode_physical_avg_pct": (
                dram_active_pct_seconds / episode_duration
                if dram_active_pct_seconds is not None and episode_duration
                else None
            ),
            "capacity_equivalent_active_seconds": (
                dram_active_pct_seconds / 100.0
                if dram_active_pct_seconds is not None
                else None
            ),
        },
        "framebuffer": {
            "used_avg_mib": window_average(
                points["fb_used_mib"], observation_start, observation_end
            ),
            "used_peak_mib": max(fb_used_samples) if fb_used_samples else None,
            "used_mib_seconds": fb_used_mib_seconds,
            "configured_capacity_utilization_avg_pct": window_average(
                points["fb_util_configured_pct"], observation_start, observation_end
            ),
            "physical_capacity_utilization_avg_pct": window_average(
                points["fb_util_physical_pct"], observation_start, observation_end
            ),
            "configured_physical_memory_avg_pct": window_average(
                points["configured_memory_pct"], observation_start, observation_end
            ),
        },
        "power": {
            "idle_avg_w": idle_power_w,
            "avg_w": energy_j / duration if energy_j is not None and duration > 0 else None,
            "observed_episode_avg_w": (
                observed_episode_energy_j / episode_duration
                if observed_episode_energy_j is not None and episode_duration
                else None
            ),
            "p95_w": percentile(power_samples, 0.95),
            "peak_w": max(power_samples) if power_samples else None,
            "deduplication": "mean per physical GPU UUID, then sum across physical GPUs",
        },
        "energy": {
            "total_j": energy_j,
            "total_wh": energy_wh,
            "dynamic_above_idle_j": dynamic_energy_j,
            "dynamic_above_idle_wh": (
                dynamic_energy_j / 3600.0 if dynamic_energy_j is not None else None
            ),
            "per_generated_token_j": (
                energy_j / total_tokens
                if energy_j is not None and total_tokens > 0
                else None
            ),
            "per_completed_request_j": (
                energy_j / len(records) if energy_j is not None and records else None
            ),
            "generated_tokens_per_j": (
                total_tokens / energy_j
                if energy_j is not None and energy_j > 0
                else None
            ),
            "generated_tokens_per_wh": (
                total_tokens / energy_wh
                if energy_wh is not None and energy_wh > 0
                else None
            ),
            "method": "idle power times workload duration plus the delayed above-idle power-pulse integral",
        },
        "useful_work": {
            "generated_tokens": total_tokens,
            "tokens_per_capacity_equivalent_sm_second": (
                total_tokens / (sm_active_pct_seconds / 100.0)
                if sm_active_pct_seconds is not None and sm_active_pct_seconds > 0
                else None
            ),
        },
        "correlations": {
            "power_vs_physical_sm_utilization_pearson_r": pearson_correlation(
                power_sm_pairs
            ),
            "power_vs_physical_sm_slope_w_per_100_percentage_points": (
                100.0 * regression_slope(power_sm_pairs)
                if regression_slope(power_sm_pairs) is not None
                else None
            ),
            "active_requests_vs_physical_sm_utilization_pearson_r": None,
            "active_requests_vs_power_pearson_r": None,
        },
        "method_notes": [
            "Raw Prometheus samples are used; query_range evaluation timestamps are avoided.",
            "The delayed GPU pulse is bounded by adjacent idle SM samples and integrated independently of HTTP timestamps.",
            "Run-average SM and DRAM values equal the delayed pulse area divided by the actual workload wall time.",
            "GR_ENGINE_ACTIVE is weighted by MIG compute slices and normalized to seven A100 compute slices for the physical-GPU view.",
            "DRAM_ACTIVE is weighted by the memory capacity encoded in GPU_I_PROFILE for the physical-GPU view.",
            "DCGM board-power copies exposed for each MIG instance are averaged per UUID and are never added together.",
            "Energy combines idle baseline over actual wall time with the delayed above-idle power-pulse integral.",
            "Runs shorter than two telemetry intervals are coarse comparative measurements, not pointwise traces.",
            "Per-request GPU attribution and request-to-GPU time correlation are disabled because delayed 5-second telemetry cannot support them.",
        ],
    }

def add_request_gpu_windows(
    per_request_stats: list[dict], rows: dict[str, list[dict]]
) -> None:
    # Five-second DCGM telemetry arrives after the HTTP activity. Mapping it to
    # individual, overlapping requests would fabricate pointwise precision.
    for request in per_request_stats:
        request["gpu_sm_avg_pct"] = None
        request["gpu_dram_avg_pct"] = None
        request["gpu_fb_used_avg_mib"] = None
        request["gpu_power_avg_w"] = None


def write_gpu_csv(rows: dict[str, list[dict]], output_file: Path) -> None:
    fieldnames = [
        "timestamp_unix_s",
        "timestamp_utc",
        "relative_to_test_start_s",
        "scope",
        "gpu_uuid",
        "gpu",
        "gpu_i_id",
        "gpu_i_profile",
        "model_name",
        "active_requests",
        "sm_partition_pct",
        "sm_configured_pct",
        "sm_physical_pct",
        "dram_partition_pct",
        "dram_configured_pct",
        "dram_physical_pct",
        "fb_used_mib",
        "fb_free_mib",
        "fb_util_partition_pct",
        "fb_util_configured_pct",
        "fb_util_physical_pct",
        "configured_compute_pct",
        "configured_memory_pct",
        "physical_memory_mib",
        "power_w",
    ]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for scope in ("partition", "physical_gpu", "system"):
            for row in rows[scope]:
                writer.writerow(
                    {
                        field: (
                            round(value, 6)
                            if isinstance((value := row.get(field)), float)
                            else value
                        )
                        for field in fieldnames
                    }
                )


def per_request_csv_path() -> Path:
    if RESULT_LOG:
        return Path(RESULT_LOG).with_suffix(".csv")
    return RESULTS_DIR / "per-request-stats.csv"


def append_per_request_stats_to_table(per_request_stats: list[dict]) -> None:
    fieldnames = [
        "idx",
        "time",
        "latency_sec",
        "tokens",
        "generation_time_sec",
        "tok_per_sec",
        "gpu_sm_avg_pct",
        "gpu_dram_avg_pct",
        "gpu_fb_used_avg_mib",
        "gpu_power_avg_w",
    ]
    output_file = per_request_csv_path()
    file_exists = output_file.exists()

    with output_file.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in per_request_stats:
            writer.writerow(
                {
                    "idx": row["idx"],
                    "time": row["time"],
                    "latency_sec": round(row["latency_sec"], 3),
                    "tokens": row["tokens"],
                    "generation_time_sec": round(row["generation_time_sec"], 3),
                    "tok_per_sec": round(row["tok_per_sec"], 3),
                    "gpu_sm_avg_pct": round_or_blank(row.get("gpu_sm_avg_pct")),
                    "gpu_dram_avg_pct": round_or_blank(row.get("gpu_dram_avg_pct")),
                    "gpu_fb_used_avg_mib": round_or_blank(
                        row.get("gpu_fb_used_avg_mib")
                    ),
                    "gpu_power_avg_w": round_or_blank(row.get("gpu_power_avg_w")),
                }
            )


def nested(summary: dict | None, *keys: str) -> object:
    value: object = summary
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def append_run_to_table(
    metadata: dict, request_summary: dict, gpu_summary: dict | None
) -> None:
    row = {
        "MIG config": metadata.get("mig_config"),
        "repliche Ollama": metadata.get("ollama_replicas"),
        "concorrenza": metadata.get("concurrency"),
        "token output": metadata.get("num_predict"),
        "Total tokens": request_summary["total_tokens"],
        "Wall time": round(request_summary["wall_time_s"], 2),
        "GPU time": round(request_summary["gpu_time_s"], 2),
        "Throughput REAL": round(request_summary["throughput_real_tok_s"], 2),
        "Throughput GPU": round(request_summary["throughput_gpu_tok_s"], 2),
        "Latency avg": round(request_summary["latency_avg_ms"], 2),
        "Latency p95": round(request_summary["latency_p95_ms"], 2),
        "GPU telemetry quality": nested(gpu_summary, "telemetry_episode", "quality"),
        "GPU active samples": nested(
            gpu_summary, "telemetry_episode", "active_sample_count"
        ),
        "GPU first-active delay (s)": round_or_blank(
            finite_float(
                nested(
                    gpu_summary,
                    "telemetry_episode",
                    "first_active_delay_from_workload_start_s",
                )
            )
        ),
        "GPU SM physical avg (%)": round_or_blank(
            finite_float(nested(gpu_summary, "sm_activity", "physical_gpu_avg_pct"))
        ),
        "GPU SM configured avg (%)": round_or_blank(
            finite_float(
                nested(gpu_summary, "sm_activity", "configured_capacity_avg_pct")
            )
        ),
        "GPU DRAM physical avg (%)": round_or_blank(
            finite_float(nested(gpu_summary, "dram_activity", "physical_gpu_avg_pct"))
        ),
        "GPU FB used avg (MiB)": round_or_blank(
            finite_float(nested(gpu_summary, "framebuffer", "used_avg_mib"))
        ),
        "GPU FB used peak (MiB)": round_or_blank(
            finite_float(nested(gpu_summary, "framebuffer", "used_peak_mib"))
        ),
        "GPU physical memory util avg (%)": round_or_blank(
            finite_float(
                nested(
                    gpu_summary,
                    "framebuffer",
                    "physical_capacity_utilization_avg_pct",
                )
            )
        ),
        "GPU power avg (W)": round_or_blank(
            finite_float(nested(gpu_summary, "power", "avg_w"))
        ),
        "GPU power p95 (W)": round_or_blank(
            finite_float(nested(gpu_summary, "power", "p95_w"))
        ),
        "GPU energy (Wh)": round_or_blank(
            finite_float(nested(gpu_summary, "energy", "total_wh")), 6
        ),
        "GPU energy/token (J)": round_or_blank(
            finite_float(nested(gpu_summary, "energy", "per_generated_token_j")),
            6,
        ),
        "Generated tokens/J": round_or_blank(
            finite_float(nested(gpu_summary, "energy", "generated_tokens_per_j")),
            6,
        ),
        "Power-SM Pearson r": round_or_blank(
            finite_float(
                nested(
                    gpu_summary,
                    "correlations",
                    "power_vs_physical_sm_utilization_pearson_r",
                )
            ),
            6,
        ),
    }
    fieldnames = list(row.keys())
    file_exists = TABLE_FILE.exists()
    with TABLE_FILE.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def print_value(label: str, value: float | None, unit: str = "", digits: int = 2) -> None:
    rendered = "n/a" if value is None else f"{value:.{digits}f}{unit}"
    print(f"{label}: {rendered}")


def main() -> int:
    records = load_records()
    metadata = load_metadata()

    total_tokens = sum(int(record["eval_count"]) for record in records)
    experiment_start_ms = min(float(record["start_time"]) for record in records)
    experiment_end_ms = max(float(record["end_time"]) for record in records)
    total_time_sec = (experiment_end_ms - experiment_start_ms) / 1000.0
    total_eval_time = sum(float(record["eval_duration"]) for record in records) / 1e9

    latencies = [float(record["total_duration"]) / 1e6 for record in records]
    tokens_per_request = [
        int(record["eval_count"]) / (float(record["eval_duration"]) / 1e9)
        for record in records
        if float(record["eval_duration"]) > 0
    ]
    throughput_real = total_tokens / total_time_sec
    throughput_gpu = total_tokens / total_eval_time
    average_tokens = statistics.fmean(tokens_per_request)
    latency_average_ms = statistics.fmean(latencies)
    latency_p95_ms = sorted(latencies)[
        min(int(len(latencies) * 0.95), len(latencies) - 1)
    ]

    per_request_stats: list[dict] = []
    for index, record in enumerate(records, start=1):
        generation_time_sec = float(record["eval_duration"]) / 1e9
        latency_sec = float(record["total_duration"]) / 1e9
        per_request_stats.append(
            {
                "idx": index,
                "time": format_created_time(record["created_at"]),
                "latency_sec": latency_sec,
                "tokens": int(record["eval_count"]),
                "generation_time_sec": generation_time_sec,
                "tok_per_sec": (
                    int(record["eval_count"]) / generation_time_sec
                    if generation_time_sec > 0
                    else 0.0
                ),
                "start_unix_s": float(record["start_time"]) / 1000.0,
                "end_unix_s": float(record["end_time"]) / 1000.0,
            }
        )

    request_summary = {
        "completed_requests": len(records),
        "total_tokens": total_tokens,
        "wall_time_s": total_time_sec,
        "gpu_time_s": total_eval_time,
        "throughput_real_tok_s": throughput_real,
        "throughput_gpu_tok_s": throughput_gpu,
        "average_tokens_per_second_per_request": average_tokens,
        "latency_avg_ms": latency_average_ms,
        "latency_p95_ms": latency_p95_ms,
    }

    gpu_rows: dict[str, list[dict]] | None = None
    gpu_summary: dict | None = None
    raw_gpu_document: dict | None = None
    if GPU_METRICS_FILE.exists():
        with GPU_METRICS_FILE.open(encoding="utf-8") as gpu_file:
            raw_gpu_document = json.load(gpu_file)
        gpu_rows = build_gpu_rows(raw_gpu_document, records)
        gpu_summary = summarize_gpu_metrics(
            raw_gpu_document, gpu_rows, records, total_tokens
        )
        add_request_gpu_windows(per_request_stats, gpu_rows)
        write_gpu_csv(gpu_rows, GPU_CSV_FILE)

    run_summary = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "test_configuration": metadata,
        "request_metrics": request_summary,
        "gpu_metrics": gpu_summary,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with RUN_SUMMARY_FILE.open("w", encoding="utf-8") as summary_file:
        json.dump(run_summary, summary_file, indent=2, sort_keys=True)
        summary_file.write("\n")

    print("\n\n--- PER-REQUEST STATS ---")
    for request in per_request_stats:
        gpu_suffix = ""
        if request.get("gpu_sm_avg_pct") is not None:
            gpu_suffix = (
                f" | GPU SM: {request['gpu_sm_avg_pct']:.2f}%"
                f" | power: {request['gpu_power_avg_w']:.2f} W"
            )
        print(
            f"Request {request['idx']:0>2} | "
            f"res_time: {request['time']} | "
            f"latency: {request['latency_sec']:6.2f} s | "
            f"tokens: {request['tokens']} | "
            f"gen_time: {request['generation_time_sec']:.3f} s | "
            f"tok/s: {request['tok_per_sec']:.2f}"
            f"{gpu_suffix}"
        )

    print("\n--- TEST CONFIGURATION ---")
    for label, key in (
        ("MIG Config", "mig_config"),
        ("Ollama Replicas", "ollama_replicas"),
        ("Total requests", "total_requests"),
        ("Concurrency", "concurrency"),
        ("Requested output tokens (effort)", "num_predict"),
    ):
        if metadata.get(key) is not None:
            print(f"{label}: {metadata[key]}")

    print(f"\nTotal tokens: {total_tokens}")
    print(f"Wall time (s): {total_time_sec:.2f}")
    print(f"GPU time (s): {total_eval_time:.2f}")

    print("\n--- REQUEST METRICS ---")
    print(f"Throughput REAL (tok/s): {throughput_real:.2f}")
    print(f"Throughput GPU (tok/s): {throughput_gpu:.2f}")
    print(f"Avg tokens/sec per request: {average_tokens:.2f}")
    print(f"Latency avg (ms): {latency_average_ms:.2f}")
    print(f"Latency p95 (ms): {latency_p95_ms:.2f}")

    if gpu_summary:
        print("\n--- GPU TELEMETRY CAPTURE ---")
        print(
            "Quality: "
            f"{nested(gpu_summary, 'telemetry_episode', 'quality')}"
        )
        print_value(
            "First active sample delay",
            finite_float(
                nested(
                    gpu_summary,
                    "telemetry_episode",
                    "first_active_delay_from_workload_start_s",
                )
            ),
            " s",
        )
        print_value(
            "Observed GPU episode duration",
            finite_float(
                nested(gpu_summary, "telemetry_episode", "duration_seconds")
            ),
            " s",
        )
        print(
            "Active telemetry samples: "
            f"{nested(gpu_summary, 'telemetry_episode', 'active_sample_count')}"
        )

        print("\n--- GPU UTILIZATION AND MEMORY ---")
        print_value(
            "Workload-normalized physical GPU SM utilization",
            finite_float(nested(gpu_summary, "sm_activity", "physical_gpu_avg_pct")),
            "%",
        )
        print_value(
            "Observed-episode physical GPU SM avg",
            finite_float(
                nested(
                    gpu_summary,
                    "sm_activity",
                    "observed_episode_physical_avg_pct",
                )
            ),
            "%",
        )
        print_value(
            "Physical GPU SM peak",
            finite_float(nested(gpu_summary, "sm_activity", "physical_gpu_peak_pct")),
            "%",
        )
        print_value(
            "Workload-normalized configured MIG SM utilization",
            finite_float(
                nested(gpu_summary, "sm_activity", "configured_capacity_avg_pct")
            ),
            "%",
        )
        print_value(
            "Workload-normalized physical GPU DRAM activity",
            finite_float(nested(gpu_summary, "dram_activity", "physical_gpu_avg_pct")),
            "%",
        )
        print_value(
            "Framebuffer used avg",
            finite_float(nested(gpu_summary, "framebuffer", "used_avg_mib")),
            " MiB",
        )
        print_value(
            "Physical framebuffer utilization avg",
            finite_float(
                nested(
                    gpu_summary,
                    "framebuffer",
                    "physical_capacity_utilization_avg_pct",
                )
            ),
            "%",
        )

        print("\n--- POWER, ENERGY, AND USEFUL WORK ---")
        print_value(
            "Idle power avg",
            finite_float(nested(gpu_summary, "power", "idle_avg_w")),
            " W",
        )
        print_value(
            "Workload-equivalent power avg",
            finite_float(nested(gpu_summary, "power", "avg_w")),
            " W",
        )
        print_value(
            "Observed-episode power avg",
            finite_float(nested(gpu_summary, "power", "observed_episode_avg_w")),
            " W",
        )
        print_value(
            "Power p95",
            finite_float(nested(gpu_summary, "power", "p95_w")),
            " W",
        )
        print_value(
            "Energy",
            finite_float(nested(gpu_summary, "energy", "total_wh")),
            " Wh",
            6,
        )
        print_value(
            "Dynamic energy above idle",
            finite_float(nested(gpu_summary, "energy", "dynamic_above_idle_j")),
            " J",
            3,
        )
        print_value(
            "Energy per generated token",
            finite_float(
                nested(gpu_summary, "energy", "per_generated_token_j")
            ),
            " J/token",
            6,
        )
        print_value(
            "Generated tokens per joule",
            finite_float(nested(gpu_summary, "energy", "generated_tokens_per_j")),
            " token/J",
            6,
        )
        print_value(
            "Power-SM Pearson correlation",
            finite_float(
                nested(
                    gpu_summary,
                    "correlations",
                    "power_vs_physical_sm_utilization_pearson_r",
                )
            ),
            "",
            4,
        )
    else:
        print("\n--- GPU METRICS ---")
        print(f"GPU telemetry unavailable: {GPU_METRICS_FILE} was not found")

    if WRITE_RUN_TO_TABLE:
        append_run_to_table(metadata, request_summary, gpu_summary)
        append_per_request_stats_to_table(per_request_stats)

        if RUN_RESULT_BASE:
            run_base = Path(RUN_RESULT_BASE)
            archived_summary = run_base.with_name(run_base.name + "-summary.json")
            shutil.copy2(RUN_SUMMARY_FILE, archived_summary)
            if raw_gpu_document is not None:
                archived_raw = run_base.with_name(run_base.name + "-gpu-metrics.json")
                archived_csv = run_base.with_name(run_base.name + "-gpu-metrics.csv")
                shutil.copy2(GPU_METRICS_FILE, archived_raw)
                shutil.copy2(GPU_CSV_FILE, archived_csv)

        print(f"\nRun appended to CSV table: {TABLE_FILE}")
        print(f"Per-request stats appended to CSV table: {per_request_csv_path()}")
        print(f"GPU time series written to: {GPU_CSV_FILE}")
        print(f"Run summary written to: {RUN_SUMMARY_FILE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
