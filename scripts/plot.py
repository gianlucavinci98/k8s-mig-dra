from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


BASE_DIR = Path(__file__).resolve().parent
INPUT_CSV = BASE_DIR / "results" / "results_table.csv"
OUTPUT_DIR = BASE_DIR / "results" / "plots"


def load_results() -> pd.DataFrame:
	df = pd.read_csv(INPUT_CSV)

	required_columns = {
		"MIG config",
		"concorrenza",
		"token output",
		"Throughput REAL",
	}
	missing_columns = required_columns - set(df.columns)
	if missing_columns:
		missing = ", ".join(sorted(missing_columns))
		raise ValueError(f"Missing required columns in {INPUT_CSV}: {missing}")

	return df


def plot_throughput(df: pd.DataFrame, token_output: int) -> Path:
	filtered = df[df["token output"] == token_output].copy()
	if filtered.empty:
		raise ValueError(f"No rows found for token output={token_output}")

	filtered["concorrenza"] = pd.to_numeric(filtered["concorrenza"], errors="coerce")
	filtered["Throughput REAL"] = pd.to_numeric(filtered["Throughput REAL"], errors="coerce")
	filtered = filtered.dropna(subset=["concorrenza", "Throughput REAL", "MIG config"])

	if filtered.empty:
		raise ValueError(f"No plottable rows found for token output={token_output}")

	profiles = sorted(filtered["MIG config"].unique())

	plt.figure(figsize=(10, 6))
	sns.set_style("whitegrid")

	for profile in profiles:
		profile_df = filtered[filtered["MIG config"] == profile].sort_values("concorrenza")
		plt.plot(
			profile_df["concorrenza"],
			profile_df["Throughput REAL"],
			marker="o",
			linewidth=2,
			label=profile,
		)

	plt.title(f"Real throughput - {token_output} output tokens")
	plt.xlabel("Numero delle chiamate")
	plt.ylabel("Real throughput")
	plt.legend(title="Profilo", frameon=True)
	plt.tight_layout()

	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	output_file = OUTPUT_DIR / f"real_throughput_{token_output}_tokens.png"
	plt.savefig(output_file, dpi=200, bbox_inches="tight")
	plt.close()
	return output_file


def main() -> None:
	df = load_results()
	outputs = [plot_throughput(df, 50), plot_throughput(df, 500)]

	for output in outputs:
		print(f"Saved plot to {output}")


if __name__ == "__main__":
	main()
