#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


BASE_DIR = Path(__file__).resolve().parent
INPUT_CSV = BASE_DIR / "results" / "results_table.csv"
OUTPUT_DIR = BASE_DIR / "results" / "plots"


def format_configuration_label(mig_config: str, ollama_replicas: int) -> str:
    profile = (
        "3g.20gb" if mig_config == "all-balanced" else mig_config.removeprefix("all-")
    )
    match = re.fullmatch(r"(\d+)g\.(\d+)gb", profile)
    if not match:
        return f"{mig_config}: {ollama_replicas} Replicas"

    compute_engines, memory_gb = match.groups()
    nicknames = {
        ("1g.5gb", 7): "Multiple Instances",
        ("3g.20gb", 1): "Restricted Instance",
        ("7g.40gb", 7): "Time-Sharing",
        ("7g.40gb", 1): "Baseline",
    }
    nickname = nicknames.get((profile, ollama_replicas))
    engine_word = "Compute Engine" if compute_engines == "1" else "Compute Engines"
    replica_word = "Replica" if ollama_replicas == 1 else "Replicas"
    label = (
        f"{compute_engines} {engine_word} | {memory_gb} GB | "
        f"{ollama_replicas} {replica_word}"
    )
    return f"{nickname} - {label}" if nickname else label


def load_results() -> pd.DataFrame:
    data = pd.read_csv(INPUT_CSV)
    required_columns = {
        "MIG config",
        "repliche Ollama",
        "concorrenza",
        "token output",
        "Throughput REAL",
    }
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns in {INPUT_CSV}: {missing}")

    data["repliche Ollama"] = pd.to_numeric(
        data["repliche Ollama"], errors="coerce"
    )
    data["concorrenza"] = pd.to_numeric(data["concorrenza"], errors="coerce")
    data["token output"] = pd.to_numeric(data["token output"], errors="coerce")
    data = data.dropna(
        subset=["MIG config", "repliche Ollama", "concorrenza", "token output"]
    )
    data["repliche Ollama"] = data["repliche Ollama"].astype(int)
    return data


def metric_for_token_output(
    data: pd.DataFrame, token_output: int, metric: str
) -> pd.DataFrame:
    if metric not in data.columns:
        return pd.DataFrame()
    filtered = data[data["token output"] == token_output].copy()
    filtered[metric] = pd.to_numeric(filtered[metric], errors="coerce")
    return filtered.dropna(subset=[metric])


def plot_metric_vs_concurrency(
    data: pd.DataFrame,
    token_output: int,
    metric: str,
    ylabel: str,
    filename: str,
) -> Path | None:
    filtered = metric_for_token_output(data, token_output, metric)
    if filtered.empty:
        return None

    grouped = (
        filtered.groupby(
            ["MIG config", "repliche Ollama", "concorrenza"], as_index=False
        )[metric]
        .agg(["mean", "std", "count"])
        .reset_index()
    )

    plt.figure(figsize=(10, 6))
    sns.set_style("whitegrid")
    series = grouped[["MIG config", "repliche Ollama"]].drop_duplicates()
    for _, series_row in series.iterrows():
        profile = series_row["MIG config"]
        replicas = int(series_row["repliche Ollama"])
        profile_data = grouped[
            (grouped["MIG config"] == profile)
            & (grouped["repliche Ollama"] == replicas)
        ].sort_values("concorrenza")
        errors = profile_data["std"].fillna(0.0)
        plt.errorbar(
            profile_data["concorrenza"],
            profile_data["mean"],
            yerr=errors,
            marker="o",
            linewidth=2,
            capsize=3,
            label=format_configuration_label(profile, replicas),
        )

    plt.title(f"Output tokens: {token_output}")
    plt.xlabel("Concurrent Requests")
    plt.ylabel(ylabel)
    plt.legend(title="Configuration", frameon=True)
    plt.tight_layout()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / filename.format(token_output=token_output)
    plt.savefig(output_file, dpi=200, bbox_inches="tight")
    plt.close()
    return output_file


def add_configuration_column(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    data["Configuration"] = data.apply(
        lambda row: format_configuration_label(
            str(row["MIG config"]), int(row["repliche Ollama"])
        ),
        axis=1,
    )
    return data


def plot_power_vs_sm(data: pd.DataFrame, token_output: int) -> Path | None:
    x_column = "GPU SM physical avg (%)"
    y_column = "GPU power avg (W)"
    if x_column not in data.columns or y_column not in data.columns:
        return None

    filtered = data[data["token output"] == token_output].copy()
    filtered[x_column] = pd.to_numeric(filtered[x_column], errors="coerce")
    filtered[y_column] = pd.to_numeric(filtered[y_column], errors="coerce")
    filtered = filtered.dropna(subset=[x_column, y_column])
    if filtered.empty:
        return None

    filtered = add_configuration_column(filtered)
    plt.figure(figsize=(10, 6))
    sns.set_style("whitegrid")
    sns.scatterplot(
        data=filtered,
        x=x_column,
        y=y_column,
        hue="Configuration",
        size="concorrenza",
        sizes=(50, 220),
        alpha=0.85,
    )
    plt.title(f"Power versus physical GPU activity — {token_output} output tokens")
    plt.xlabel("Physical GPU SM Utilization (%)")
    plt.ylabel("Average Board Power (W)")
    plt.tight_layout()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"power-vs-sm-{token_output}-tokens.png"
    plt.savefig(output_file, dpi=200, bbox_inches="tight")
    plt.close()
    return output_file


def plot_useful_work_efficiency(
    data: pd.DataFrame, token_output: int
) -> Path | None:
    x_column = "Throughput REAL"
    y_column = "GPU energy/token (J)"
    if y_column not in data.columns:
        return None

    filtered = data[data["token output"] == token_output].copy()
    filtered[x_column] = pd.to_numeric(filtered[x_column], errors="coerce")
    filtered[y_column] = pd.to_numeric(filtered[y_column], errors="coerce")
    filtered = filtered.dropna(subset=[x_column, y_column])
    if filtered.empty:
        return None

    filtered = add_configuration_column(filtered)
    plt.figure(figsize=(10, 6))
    sns.set_style("whitegrid")
    sns.scatterplot(
        data=filtered,
        x=x_column,
        y=y_column,
        hue="Configuration",
        size="concorrenza",
        sizes=(50, 220),
        alpha=0.85,
    )
    plt.title(f"Useful work and energy efficiency — {token_output} output tokens")
    plt.xlabel("User Throughput (token/s)")
    plt.ylabel("GPU Energy per Generated Token (J/token, lower is better)")
    plt.tight_layout()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"throughput-vs-energy-per-token-{token_output}.png"
    plt.savefig(output_file, dpi=200, bbox_inches="tight")
    plt.close()
    return output_file


def main() -> None:
    data = load_results()
    token_outputs = sorted(data["token output"].dropna().astype(int).unique())
    outputs: list[Path] = []

    for token_output in token_outputs:
        candidates = [
            plot_metric_vs_concurrency(
                data,
                token_output,
                "Throughput REAL",
                "User Throughput (token/s)",
                "real-throughput-{token_output}-tokens.png",
            ),
            plot_metric_vs_concurrency(
                data,
                token_output,
                "GPU SM physical avg (%)",
                "Physical GPU SM Utilization (%)",
                "sm-utilization-{token_output}-tokens.png",
            ),
            plot_metric_vs_concurrency(
                data,
                token_output,
                "GPU power avg (W)",
                "Average Board Power (W)",
                "power-{token_output}-tokens.png",
            ),
            plot_metric_vs_concurrency(
                data,
                token_output,
                "GPU energy/token (J)",
                "GPU Energy per Generated Token (J/token)",
                "energy-per-token-{token_output}-tokens.png",
            ),
            plot_power_vs_sm(data, token_output),
            plot_useful_work_efficiency(data, token_output),
        ]
        outputs.extend(output for output in candidates if output is not None)

    for output in outputs:
        print(f"Saved plot to {output}")


if __name__ == "__main__":
    main()
