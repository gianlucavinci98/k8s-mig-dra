#!/usr/bin/env python3
"""Compare makespan distributions produced by the experiment arm runners."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def describe(values: list[float]) -> dict[str, float | int]:
    return {
        "replicas": len(values),
        "min_seconds": min(values),
        "p50_seconds": percentile(values, 0.50),
        "p95_seconds": percentile(values, 0.95),
        "max_seconds": max(values),
        "mean_seconds": sum(values) / len(values),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    makespans: dict[str, list[float]] = defaultdict(list)
    sources: dict[str, list[str]] = defaultdict(list)
    for path in args.summaries:
        with path.open(encoding="utf-8") as handle:
            summary = json.load(handle)
        arm = summary.get("experiment_arm")
        makespan = summary.get("makespan_seconds")
        if not arm or makespan is None:
            raise ValueError(f"{path} does not contain experiment_arm and makespan_seconds")
        makespans[str(arm)].append(float(makespan))
        sources[str(arm)].append(str(path.resolve()))

    arms = {arm: describe(values) for arm, values in sorted(makespans.items())}
    comparisons: dict[str, dict[str, float]] = {}
    if "d-flex" in arms:
        dflex_p50 = float(arms["d-flex"]["p50_seconds"])
        for baseline in ("baseline-medium", "baseline-large", "baseline-mix"):
            if baseline not in arms:
                continue
            baseline_p50 = float(arms[baseline]["p50_seconds"])
            comparisons[f"d-flex_vs_{baseline}"] = {
                "baseline_p50_seconds": baseline_p50,
                "dflex_p50_seconds": dflex_p50,
                "seconds_saved": baseline_p50 - dflex_p50,
                "makespan_reduction_percent": (
                    (baseline_p50 - dflex_p50) / baseline_p50 * 100.0
                ),
                "speedup": baseline_p50 / dflex_p50,
            }

    report = {
        "comparison_basis": "p50 of independent pool-replica makespans",
        "arms": arms,
        "comparisons": comparisons,
        "sources": sources,
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
