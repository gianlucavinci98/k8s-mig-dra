import json

file = "results.jsonl"

records = []
with open(file) as f:
    for line in f:
        records.append(json.loads(line))

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

# --- OUTPUT ---

print("\n\n--- PER-REQUEST STATS ---")
for s in per_request_stats:
    print(
        f"Request #{s['idx']:>1} | "
        f"res_time: {s['time']} | "
        f"latency: {s['latency_sec']:.2f} s | "
        f"tokens: {s['tokens']} | "
        f"gen_time: {s['generation_time_sec']:.3f} s | "
        f"tok/s: {s['tok_per_sec']:.2f}"
    )

print(f"\nTotal tokens: {total_tokens}")
print(f"Wall time (s): {total_time_sec:.2f}")
print(f"GPU time (s): {total_eval_time:.2f}")

print("\n--- METRICS ---")
print(f"Throughput REAL (tok/s): {throughput_real:.2f}")
print(f"Throughput GPU (tok/s): {throughput_gpu:.2f}")
print(f"Avg tokens/sec per request: {avg_tokens:.2f}")

print(f"Latency avg (ms): {sum(latencies)/len(latencies):.2f}")
print(f"Latency p95 (ms): {sorted(latencies)[min(int(len(latencies)*0.95), len(latencies)-1)]:.2f}")