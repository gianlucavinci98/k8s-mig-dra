from pathlib import Path
import re

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


BASE_DIR = Path(__file__).resolve().parent
INPUT_CSV = BASE_DIR / "results" / "results_table.csv"
OUTPUT_DIR = BASE_DIR / "results" / "plots"


def format_configuration_label(mig_config: str, ollama_replicas: int) -> str:
	match = re.search(r"(\d+)g", mig_config)
	ce_count = match.group(1) if match else mig_config
	replica_word = "replica" if ollama_replicas == 1 else "repliche"
	return f"{mig_config}+{ollama_replicas} {replica_word} = {ce_count} CE + {ollama_replicas} Rep"


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


def plot_throughput(df: pd.DataFrame, token_output: int) -> Path:
	token_output_values = pd.to_numeric(df["token output"], errors="coerce")
	filtered = df[token_output_values == token_output].copy()
	if filtered.empty:
		raise ValueError(f"No rows found for token output={token_output}")

	filtered["repliche Ollama"] = pd.to_numeric(filtered["repliche Ollama"], errors="coerce")
	filtered["concorrenza"] = pd.to_numeric(filtered["concorrenza"], errors="coerce")
	filtered["Throughput REAL"] = pd.to_numeric(filtered["Throughput REAL"], errors="coerce")
	filtered = filtered.dropna(subset=["repliche Ollama", "concorrenza", "Throughput REAL", "MIG config"])

	if filtered.empty:
		raise ValueError(f"No plottable rows found for token output={token_output}")

	filtered["repliche Ollama"] = filtered["repliche Ollama"].astype(int)
	series = filtered[["MIG config", "repliche Ollama"]].drop_duplicates().sort_values(["MIG config", "repliche Ollama"])

	plt.figure(figsize=(10, 6))
	sns.set_style("whitegrid")

	for _, row in series.iterrows():
		profile = row["MIG config"]
		replicas = int(row["repliche Ollama"])
		profile_df = filtered[
			(filtered["MIG config"] == profile) & (filtered["repliche Ollama"] == replicas)
		].sort_values("concorrenza")
		plt.plot(
			profile_df["concorrenza"],
			profile_df["Throughput REAL"],
			marker="o",
			linewidth=2,
			label=format_configuration_label(profile, replicas),
		)

	plt.title(f"Output tokens: {token_output}")
	plt.xlabel("Concurrency (number of simultaneous requests).")
	plt.ylabel("User Throughput (tok/s)")
	plt.legend(title="Configuration", frameon=True)
	plt.tight_layout()

	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	output_file = OUTPUT_DIR / f"real_throughput_{token_output}_tokens.png"
	plt.savefig(output_file, dpi=200, bbox_inches="tight")
	plt.close()
	return output_file


def main() -> None:
	df = load_results()
	token_outputs = sorted(pd.to_numeric(df["token output"], errors="coerce").dropna().astype(int).unique())
	outputs = [plot_throughput(df, token_output) for token_output in token_outputs]

	for output in outputs:
		print(f"Saved plot to {output}")


if __name__ == "__main__":
	main()
