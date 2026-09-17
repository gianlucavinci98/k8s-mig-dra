#!/usr/bin/env python3
"""Generate dependency-free SVG figures and derived CSVs for the Ollama report."""

from __future__ import annotations

import csv
import html
import math
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
OUTPUT_DIR = RESULTS_DIR / "report-assets"
TABLE_FILE = RESULTS_DIR / "results_table.csv"

CASE_ORDER = [
    "Baseline",
    "Restricted instance",
    "Time-sharing",
    "Multiple instances",
]

CASE_COLORS = {
    "Baseline": "#3b5b92",
    "Restricted instance": "#d17b0f",
    "Time-sharing": "#8c5aa8",
    "Multiple instances": "#17855b",
    "Throughput gain": "#17855b",
    "p95 latency reduction": "#b24c63",
}

CASE_BY_CONFIG = {
    ("all-7g.40gb", 1): "Baseline",
    ("all-balanced", 1): "Restricted instance",
    ("all-7g.40gb", 7): "Time-sharing",
    ("all-1g.5gb", 7): "Multiple instances",
}


def load_main_table() -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    with TABLE_FILE.open(newline="") as handle:
        for source in csv.DictReader(handle):
            replicas = int(source["repliche Ollama"])
            key = (source["MIG config"], replicas)
            if key not in CASE_BY_CONFIG or int(source["token output"]) != 25:
                continue
            rows.append(
                {
                    "case": CASE_BY_CONFIG[key],
                    "mig_config": source["MIG config"],
                    "replicas": replicas,
                    "concurrency": int(source["concorrenza"]),
                    "tokens": int(source["Total tokens"]),
                    "wall_time": float(source["Wall time"]),
                    "gpu_time": float(source["GPU time"]),
                    "throughput_real": float(source["Throughput REAL"]),
                    "throughput_gpu": float(source["Throughput GPU"]),
                    "latency_avg_ms": float(source["Latency avg"]),
                    "latency_p95_ms": float(source["Latency p95"]),
                }
            )
    return sorted(rows, key=lambda row: (CASE_ORDER.index(str(row["case"])), int(row["concurrency"])))


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def load_request_rows() -> dict[tuple[str, int], list[dict[str, float]]]:
    pattern = re.compile(
        r"result-\d{8}-\d{6}-\d{3}-(.+)-replicas(\d+)-25\.csv$"
    )
    runs: dict[tuple[str, int], list[dict[str, float]]] = {}
    for path in sorted(RESULTS_DIR.glob("result-*.csv")):
        match = pattern.fullmatch(path.name)
        if not match:
            continue
        config = match.group(1)
        replicas = int(match.group(2))
        case = CASE_BY_CONFIG.get((config, replicas))
        if case is None:
            continue

        log_text = path.with_suffix(".log").read_text(errors="replace")
        concurrency_matches = re.findall(r"^Concurrency: (\d+)$", log_text, re.MULTILINE)
        if not concurrency_matches:
            raise ValueError(f"Cannot find concurrency in {path.with_suffix('.log')}")
        concurrency = int(concurrency_matches[-1])

        with path.open(newline="") as handle:
            rows = [
                {
                    "latency_sec": float(row["latency_sec"]),
                    "generation_time_sec": float(row["generation_time_sec"]),
                    "tok_per_sec": float(row["tok_per_sec"]),
                }
                for row in csv.DictReader(handle)
            ]
        runs[(case, concurrency)] = rows
    return runs


def nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exponent = 10 ** math.floor(math.log10(value))
    fraction = value / exponent
    if fraction <= 1:
        nice_fraction = 1
    elif fraction <= 2:
        nice_fraction = 2
    elif fraction <= 5:
        nice_fraction = 5
    else:
        nice_fraction = 10
    return nice_fraction * exponent


def svg_text(
    x: float,
    y: float,
    text: str,
    *,
    size: int = 13,
    anchor: str = "middle",
    weight: str = "normal",
    fill: str = "#243042",
    rotate: int | None = None,
) -> str:
    transform = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate is not None else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}"{transform}>'
        f"{html.escape(text)}</text>"
    )


def line_chart(
    output: Path,
    series: dict[str, list[tuple[float, float]]],
    *,
    title: str,
    x_label: str,
    y_label: str,
    y_max: float | None = None,
    y_ticks: int = 5,
    y_formatter=lambda value: f"{value:.0f}",
    x_values: list[float] | None = None,
) -> None:
    width, height = 1120, 680
    left, right, top, bottom = 105, 35, 75, 105
    plot_w = width - left - right
    plot_h = height - top - bottom
    all_points = [point for points in series.values() for point in points]
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    x_min, x_max = min(xs), max(xs)
    y_min = 0.0
    y_max = y_max if y_max is not None else nice_max(max(ys) * 1.05)

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 36, title, size=22, weight="bold"),
    ]

    for index in range(y_ticks + 1):
        value = y_min + (y_max - y_min) * index / y_ticks
        y = sy(value)
        elements.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            'stroke="#dfe5ec" stroke-width="1"/>'
        )
        elements.append(svg_text(left - 12, y + 5, y_formatter(value), anchor="end"))

    ticks = x_values if x_values is not None else sorted(set(xs))
    for value in ticks:
        x = sx(value)
        elements.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" '
            'stroke="#eff2f6" stroke-width="1"/>'
        )
        elements.append(svg_text(x, top + plot_h + 27, f"{value:g}"))

    elements.extend(
        [
            f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#526273" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#526273" stroke-width="1.5"/>',
            svg_text(left + plot_w / 2, height - 30, x_label, size=15),
            svg_text(27, top + plot_h / 2, y_label, size=15, rotate=-90),
        ]
    )

    for name, points in series.items():
        color = CASE_COLORS.get(name, "#4c6278")
        coords = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
        elements.append(
            f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3.5" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        for x, y in points:
            elements.append(
                f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5" fill="#ffffff" '
                f'stroke="{color}" stroke-width="3"/>'
            )

    legend_x = left + 18
    legend_y = top + 18
    legend_width = 265
    legend_height = 28 * len(series) + 18
    elements.append(
        f'<rect x="{legend_x}" y="{legend_y}" width="{legend_width}" height="{legend_height}" '
        'rx="6" fill="#ffffff" fill-opacity="0.94" stroke="#c8d0da"/>'
    )
    for index, name in enumerate(series):
        y = legend_y + 24 + index * 28
        color = CASE_COLORS.get(name, "#4c6278")
        elements.append(
            f'<line x1="{legend_x + 14}" y1="{y}" x2="{legend_x + 48}" y2="{y}" '
            f'stroke="{color}" stroke-width="4"/>'
        )
        elements.append(svg_text(legend_x + 58, y + 5, name, anchor="start", size=13))

    elements.append("</svg>")
    output.write_text("\n".join(elements) + "\n")


def ecdf_chart(
    output: Path,
    request_rows: dict[tuple[str, int], list[dict[str, float]]],
) -> None:
    width, height = 1120, 680
    left, right, top, bottom = 105, 35, 75, 105
    plot_w = width - left - right
    plot_h = height - top - bottom
    x_min, x_max = 0.0, 50.0

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return top + plot_h - value / 100 * plot_h

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        svg_text(width / 2, 36, "Latency distribution at 500 concurrent requests", size=22, weight="bold"),
    ]
    for value in range(0, 101, 20):
        y = sy(value)
        elements.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#dfe5ec"/>'
        )
        elements.append(svg_text(left - 12, y + 5, f"{value}%", anchor="end"))
    for value in range(0, 51, 10):
        x = sx(value)
        elements.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" stroke="#eff2f6"/>'
        )
        elements.append(svg_text(x, top + plot_h + 27, str(value)))

    elements.extend(
        [
            f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#526273" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#526273" stroke-width="1.5"/>',
            svg_text(left + plot_w / 2, height - 30, "Per-request latency (s)", size=15),
            svg_text(27, top + plot_h / 2, "Completed requests", size=15, rotate=-90),
        ]
    )

    for case in CASE_ORDER:
        values = sorted(row["latency_sec"] for row in request_rows[(case, 500)])
        points = [(value, (index + 1) / len(values) * 100) for index, value in enumerate(values)]
        color = CASE_COLORS[case]
        path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
        elements.append(
            f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="3" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )

    legend_x = left + 18
    legend_y = top + 18
    elements.append(
        f'<rect x="{legend_x}" y="{legend_y}" width="265" height="130" rx="6" '
        'fill="#ffffff" fill-opacity="0.94" stroke="#c8d0da"/>'
    )
    for index, case in enumerate(CASE_ORDER):
        y = legend_y + 24 + index * 28
        elements.append(
            f'<line x1="{legend_x + 14}" y1="{y}" x2="{legend_x + 48}" y2="{y}" '
            f'stroke="{CASE_COLORS[case]}" stroke-width="4"/>'
        )
        elements.append(svg_text(legend_x + 58, y + 5, case, anchor="start", size=13))
    elements.append("</svg>")
    output.write_text("\n".join(elements) + "\n")


def write_derived_tables(
    rows: list[dict[str, float | int | str]],
    request_rows: dict[tuple[str, int], list[dict[str, float]]],
) -> None:
    with (OUTPUT_DIR / "main-results-derived.csv").open("w", newline="") as handle:
        fields = [
            "case",
            "concurrency",
            "wall_time_s",
            "throughput_real_tok_s",
            "throughput_gpu_tok_s",
            "latency_avg_s",
            "latency_p95_s",
            "generation_avg_s",
            "non_generation_avg_s",
            "non_generation_share_pct",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            case = str(row["case"])
            concurrency = int(row["concurrency"])
            requests = request_rows[(case, concurrency)]
            latency_avg = sum(item["latency_sec"] for item in requests) / len(requests)
            generation_avg = sum(item["generation_time_sec"] for item in requests) / len(requests)
            non_generation = latency_avg - generation_avg
            writer.writerow(
                {
                    "case": case,
                    "concurrency": concurrency,
                    "wall_time_s": row["wall_time"],
                    "throughput_real_tok_s": row["throughput_real"],
                    "throughput_gpu_tok_s": row["throughput_gpu"],
                    "latency_avg_s": f"{latency_avg:.6f}",
                    "latency_p95_s": f"{float(row['latency_p95_ms']) / 1000:.6f}",
                    "generation_avg_s": f"{generation_avg:.6f}",
                    "non_generation_avg_s": f"{non_generation:.6f}",
                    "non_generation_share_pct": f"{non_generation / latency_avg * 100:.3f}",
                }
            )

    by_key = {(str(row["case"]), int(row["concurrency"])): row for row in rows}
    with (OUTPUT_DIR / "relative-vs-baseline.csv").open("w", newline="") as handle:
        fields = [
            "case",
            "concurrency",
            "throughput_change_pct",
            "wall_time_change_pct",
            "latency_avg_change_pct",
            "latency_p95_change_pct",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for concurrency in [10, 100, 200, 300, 400, 500]:
            baseline = by_key[("Baseline", concurrency)]
            for case in CASE_ORDER[1:]:
                row = by_key[(case, concurrency)]
                writer.writerow(
                    {
                        "case": case,
                        "concurrency": concurrency,
                        "throughput_change_pct": f"{(float(row['throughput_real']) / float(baseline['throughput_real']) - 1) * 100:.3f}",
                        "wall_time_change_pct": f"{(float(row['wall_time']) / float(baseline['wall_time']) - 1) * 100:.3f}",
                        "latency_avg_change_pct": f"{(float(row['latency_avg_ms']) / float(baseline['latency_avg_ms']) - 1) * 100:.3f}",
                        "latency_p95_change_pct": f"{(float(row['latency_p95_ms']) / float(baseline['latency_p95_ms']) - 1) * 100:.3f}",
                    }
                )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_main_table()
    request_rows = load_request_rows()
    by_case = {
        case: [row for row in rows if row["case"] == case]
        for case in CASE_ORDER
    }
    concurrency_values = [10, 100, 200, 300, 400, 500]

    line_chart(
        OUTPUT_DIR / "throughput-real-vs-concurrency.svg",
        {
            case: [(float(row["concurrency"]), float(row["throughput_real"])) for row in by_case[case]]
            for case in CASE_ORDER
        },
        title="User-perceived throughput (25 output tokens)",
        x_label="Concurrent requests",
        y_label="Throughput REAL (tok/s)",
        y_max=750,
        x_values=concurrency_values,
    )
    line_chart(
        OUTPUT_DIR / "wall-time-vs-concurrency.svg",
        {
            case: [(float(row["concurrency"]), float(row["wall_time"])) for row in by_case[case]]
            for case in CASE_ORDER
        },
        title="Batch wall time (25 output tokens per request)",
        x_label="Concurrent requests",
        y_label="Wall time (s)",
        y_max=55,
        x_values=concurrency_values,
    )
    line_chart(
        OUTPUT_DIR / "latency-p95-vs-concurrency.svg",
        {
            case: [(float(row["concurrency"]), float(row["latency_p95_ms"]) / 1000) for row in by_case[case]]
            for case in CASE_ORDER
        },
        title="Tail latency (25 output tokens)",
        x_label="Concurrent requests",
        y_label="Reported latency p95 (s)",
        y_max=50,
        x_values=concurrency_values,
    )
    ecdf_chart(OUTPUT_DIR / "latency-ecdf-c500.svg", request_rows)

    baseline_by_concurrency = {
        int(row["concurrency"]): row for row in by_case["Baseline"]
    }
    multiple_by_concurrency = {
        int(row["concurrency"]): row for row in by_case["Multiple instances"]
    }
    line_chart(
        OUTPUT_DIR / "multiple-instances-gain-vs-baseline.svg",
        {
            "Throughput gain": [
                (
                    concurrency,
                    (
                        float(multiple_by_concurrency[concurrency]["throughput_real"])
                        / float(baseline_by_concurrency[concurrency]["throughput_real"])
                        - 1
                    )
                    * 100,
                )
                for concurrency in concurrency_values
            ],
            "p95 latency reduction": [
                (
                    concurrency,
                    (
                        1
                        - float(multiple_by_concurrency[concurrency]["latency_p95_ms"])
                        / float(baseline_by_concurrency[concurrency]["latency_p95_ms"])
                    )
                    * 100,
                )
                for concurrency in concurrency_values
            ],
        },
        title="Multiple Instances advantage over Baseline",
        x_label="Concurrent requests",
        y_label="Improvement (%)",
        y_max=140,
        x_values=concurrency_values,
    )

    write_derived_tables(rows, request_rows)
    for path in sorted(OUTPUT_DIR.iterdir()):
        print(path.relative_to(BASE_DIR))


if __name__ == "__main__":
    main()
