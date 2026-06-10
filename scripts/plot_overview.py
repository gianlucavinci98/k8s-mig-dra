from __future__ import annotations

from math import ceil
from pathlib import Path
import re

import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
import pandas as pd
import seaborn as sns
from matplotlib import colormaps
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


BASE_DIR = Path(__file__).resolve().parent
INPUT_CSV = BASE_DIR / "results" / "results_table.csv"
OUTPUT_DIR = BASE_DIR / "results" / "plots"
OUTPUT_FILE = OUTPUT_DIR / "throughput_overview.png"


def format_configuration_label(mig_config: str, ollama_replicas: int) -> str:
	match = re.search(r"(\d+)g", mig_config)
	ce_count = match.group(1) if match else mig_config
	replica_word = "replica" if ollama_replicas == 1 else "repliche"
	return f"{mig_config} + {ollama_replicas} {replica_word} = {ce_count} CE + {ollama_replicas} Rep"


def load_results() -> pd.DataFrame:
	df = pd.read_csv(INPUT_CSV)

	required_columns = {
		"MIG config",
		"repliche Ollama",
		"concorrenza",
		"token output",
		"Throughput REAL",
	}
	missing_columns = required_columns - set(df.columns)
	if missing_columns:
		missing = ", ".join(sorted(missing_columns))
		raise ValueError(f"Missing required columns in {INPUT_CSV}: {missing}")

	return df


def normalize_results(df: pd.DataFrame) -> pd.DataFrame:
	normalized = df.copy()
	normalized["repliche Ollama"] = pd.to_numeric(normalized["repliche Ollama"], errors="coerce")
	normalized["concorrenza"] = pd.to_numeric(normalized["concorrenza"], errors="coerce")
	normalized["token output"] = pd.to_numeric(normalized["token output"], errors="coerce")
	normalized["Throughput REAL"] = pd.to_numeric(normalized["Throughput REAL"], errors="coerce")
	normalized = normalized.dropna(subset=["MIG config", "repliche Ollama", "concorrenza", "token output", "Throughput REAL"])
	normalized["repliche Ollama"] = normalized["repliche Ollama"].astype(int)
	normalized["concorrenza"] = normalized["concorrenza"].astype(int)
	normalized["token output"] = normalized["token output"].astype(int)
	return normalized


def build_configuration_order(df: pd.DataFrame) -> pd.DataFrame:
	return df[["MIG config", "repliche Ollama"]].drop_duplicates().sort_values([
		"MIG config",
		"repliche Ollama",
	])


def plot_overview(df: pd.DataFrame) -> Path:
	if df.empty:
		raise ValueError(f"No rows found in {INPUT_CSV}")

	configurations = build_configuration_order(df)
	num_configs = len(configurations)
	if num_configs == 0:
		raise ValueError("No configurations found in the results table")

	n_cols = min(2, num_configs)
	n_rows = ceil(num_configs / n_cols)

	fig, axes = plt.subplots(
		n_rows,
		n_cols,
		figsize=(7.5 * n_cols, 4.5 * n_rows),
		sharex=True,
		sharey=True,
		constrained_layout=False,
		subplot_kw={"projection": "3d"},
	)
	axes_list = axes.flatten() if hasattr(axes, "flatten") else [axes]

	global_min = df["Throughput REAL"].min()
	global_max = df["Throughput REAL"].max()
	normalizer = Normalize(vmin=global_min, vmax=global_max)
	color_map = colormaps["viridis"]
	bar_width = 0.8
	bar_depth = 0.8

	for axis, (_, config_row) in zip(axes_list, configurations.iterrows()):
		mig_config = config_row["MIG config"]
		replicas = int(config_row["repliche Ollama"])
		config_df = df[
			(df["MIG config"] == mig_config) & (df["repliche Ollama"] == replicas)
		]
		config_df = config_df.sort_values(["concorrenza", "token output"])

		x_positions = config_df["concorrenza"].to_numpy(dtype=float)
		y_positions = config_df["token output"].to_numpy(dtype=float)
		heights = config_df["Throughput REAL"].to_numpy(dtype=float)
		colors = color_map(normalizer(heights))

		axis.bar3d(
			x_positions - bar_width / 2,
			y_positions - bar_depth / 2,
			0,
			bar_width,
			bar_depth,
			heights,
			color=colors,
			shade=True,
			alpha=0.95,
			zsort="average",
		)
		axis.set_title(format_configuration_label(mig_config, replicas))
		axis.set_xlabel("Concurrency")
		axis.set_ylabel("Output tokens")
		axis.set_zlabel("User Throughput (tok/s)")
		axis.view_init(elev=24, azim=-60)
		axis.tick_params(axis="x", rotation=0)
		axis.tick_params(axis="y", rotation=0)
		axis.set_zlim(global_min * 0.95, global_max * 1.05)

	for axis in axes_list[num_configs:]:
		axis.set_visible(False)

	fig.supxlabel("Concurrency (number of simultaneous requests).")
	fig.supylabel("Output tokens")
	fig.suptitle("User Throughput (tok/s) overview", y=0.98)

	if num_configs > 0:
		colorbar = fig.colorbar(
			ScalarMappable(norm=normalizer, cmap=color_map),
			ax=axes_list[:num_configs],
			shrink=0.9,
			pad=0.02,
		)
		colorbar.set_label("User Throughput (tok/s)")

	fig.subplots_adjust(left=0.08, right=0.88, bottom=0.09, top=0.90, wspace=0.20, hspace=0.32)
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	fig.savefig(OUTPUT_FILE, dpi=200, bbox_inches="tight")
	plt.close(fig)
	return OUTPUT_FILE


def main() -> None:
	results = normalize_results(load_results())
	output = plot_overview(results)
	print(f"Saved plot to {output}")


if __name__ == "__main__":
	main()