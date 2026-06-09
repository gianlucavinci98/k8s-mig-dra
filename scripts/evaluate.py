import json
import os
import csv
from pathlib import Path

file = "results/results.jsonl"
metadata_file = "results/metadata.json"
table_file = "results/results_table.csv"

def env_flag_is_enabled(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


# Follow the same switch used to persist RESULT_LOG.
WRITE_RUN_TO_TABLE = env_flag_is_enabled(os.environ.get("SAVE_RESULT_LOG"))
RESULT_LOG = os.environ.get("RESULT_LOG")

records = []
with open(file) as f:
    for line in f:
        records.append(json.loads(line))

# Load metadata if available
metadata = {}
if os.path.exists(metadata_file):
    with open(metadata_file) as f:
        metadata = json.load(f)

num_predict = metadata.get("num_predict")
mig_config = metadata.get("mig_config")
ollama_replicas = metadata.get("ollama_replicas")
total_requests = metadata.get("total_requests")
concurrency = metadata.get("concurrency")

# --- METRICHE BASE ---

total_tokens = sum(r["eval_count"] for r in records)

# wall clock dell'esperimento basato sul primo start e sull'ultimo end
experiment_start_ms = min(r["start_time"] for r in records)
experiment_end_ms = max(r["end_time"] for r in records)
total_time_sec = (experiment_end_ms - experiment_start_ms) / 1000

# somma tempi GPU
total_eval_time = sum(r["eval_duration"] for r in records) / 1e9  # ns -> s


def format_created_time(created_at: str) -> str:
    # Formato richiesto: HH:MM:SS.xx
    time_part = created_at.split("T", 1)[1].rstrip("Z")
    if "." not in time_part:
        return f"{time_part}.00"

    hms, frac = time_part.split(".", 1)
    hundredths = frac[:2].ljust(2, "0")
    return f"{hms}.{hundredths}"

# --- METRICHE RICHIESTE ---

# 1) latenza per richiesta
latencies = [r["total_duration"] / 1e6 for r in records]

# 2) tokens/sec per richiesta
tokens_per_req = [
    r["eval_count"] / (r["eval_duration"] / 1e9)
    for r in records if r["eval_duration"] > 0
]

# dettagli per richiesta (human readable)
per_request_stats = []
for idx, r in enumerate(records, start=1):
    generation_time_sec = r["eval_duration"] / 1e9
    latency_sec = r["total_duration"] / 1e9
    tok_per_sec = (
        r["eval_count"] / generation_time_sec if generation_time_sec > 0 else 0.0
    )
    per_request_stats.append(
        {
            "idx": idx,
            "time": format_created_time(r["created_at"]),
            "latency_sec": latency_sec,
            "tokens": r["eval_count"],
            "generation_time_sec": generation_time_sec,
            "tok_per_sec": tok_per_sec,
        }
    )

# 3) throughput reale
throughput_real = total_tokens / total_time_sec

# 4) throughput GPU
throughput_gpu = total_tokens / total_eval_time

# 5) media tokens/sec
avg_tokens = sum(tokens_per_req) / len(tokens_per_req)

latency_avg_ms = sum(latencies) / len(latencies)
latency_p95_ms = sorted(latencies)[min(int(len(latencies) * 0.95), len(latencies) - 1)]


def per_request_csv_path() -> Path:
    if RESULT_LOG:
        return Path(RESULT_LOG).with_suffix(".csv")

    return Path("results") / "per-request-stats.csv"


def append_per_request_stats_to_table() -> None:
    fieldnames = [
        "idx",
        "time",
        "latency_sec",
        "tokens",
        "generation_time_sec",
        "tok_per_sec",
    ]

    output_file = per_request_csv_path()
    file_exists = output_file.exists()

    with output_file.open("a", newline="") as csv_file:
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
                }
            )


def append_run_to_table() -> None:
    row = {
        "MIG config": mig_config,
        "repliche Ollama": ollama_replicas,
        "concorrenza": concurrency,
        "token output": num_predict,
        "Total tokens": total_tokens,
        "Wall time": round(total_time_sec, 2),
        "GPU time": round(total_eval_time, 2),
        "Throughput REAL": round(throughput_real, 2),
        "Throughput GPU": round(throughput_gpu, 2),
        "Latency avg": round(latency_avg_ms, 2),
        "Latency p95": round(latency_p95_ms, 2),
    }

    fieldnames = list(row.keys())
    file_exists = os.path.exists(table_file)

    with open(table_file, "a", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

# --- OUTPUT ---

print("\n\n--- PER-REQUEST STATS ---")
for s in per_request_stats:
    print(
        f"Request {s['idx']:0>2} | "
        f"res_time: {s['time']} | "
        f"latency: {s['latency_sec']:6.2f} s | "
        f"tokens: {s['tokens']} | "
        f"gen_time: {s['generation_time_sec']:.3f} s | "
        f"tok/s: {s['tok_per_sec']:.2f}"
    )

print("\n--- TEST CONFIGURATION ---")
if mig_config:
    print(f"MIG Config: {mig_config}")
if ollama_replicas is not None:
    print(f"Ollama Replicas: {ollama_replicas}")
if total_requests is not None:
    print(f"Total requests: {total_requests}")
if concurrency is not None:
    print(f"Concurrency: {concurrency}")
if num_predict is not None:
    print(f"Requested output tokens (effort): {num_predict}")

print(f"\nTotal tokens: {total_tokens}")
print(f"Wall time (s): {total_time_sec:.2f}")
print(f"GPU time (s): {total_eval_time:.2f}")

print("\n--- METRICS ---")
print(f"Throughput REAL (tok/s): {throughput_real:.2f}")
print(f"Throughput GPU (tok/s): {throughput_gpu:.2f}")
print(f"Avg tokens/sec per request: {avg_tokens:.2f}")

print(f"Latency avg (ms): {latency_avg_ms:.2f}")
print(f"Latency p95 (ms): {latency_p95_ms:.2f}")

if WRITE_RUN_TO_TABLE:
    append_run_to_table()
    append_per_request_stats_to_table()
    print(f"\nRun appended to CSV table: {table_file}")
    print(f"Per-request stats appended to CSV table: {per_request_csv_path()}")