#!/bin/bash

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

URL="http://10.146.0.55:31134/api/generate"
MODEL="tinyllama"
NUM_PREDICT="${NUM_PREDICT:-25}"

PROMETHEUS_URL="${PROMETHEUS_URL:-http://10.146.0.55:30090}"
PROMETHEUS_STEP_SECONDS="${PROMETHEUS_STEP_SECONDS:-5}"
PROMETHEUS_PADDING_BEFORE_SECONDS="${PROMETHEUS_PADDING_BEFORE_SECONDS:-15}"
PROMETHEUS_PADDING_AFTER_SECONDS="${PROMETHEUS_PADDING_AFTER_SECONDS:-5}"
PROMETHEUS_SCRAPE_WAIT_SECONDS="${PROMETHEUS_SCRAPE_WAIT_SECONDS:-6}"

TEST_MIG_CONFIG="$(kubectl get nodes -o json | jq -r '.items[].metadata.labels["nvidia.com/mig.config"] // empty' | awk 'NF { print; exit }')"
TEST_OLLAMA_REPLICAS="$(kubectl -n ollama-test get deploy ollama-mig -o jsonpath='{.spec.replicas}' 2>/dev/null)"

TEST_MIG_CONFIG="${TEST_MIG_CONFIG:-unknown-mig-config}"
TEST_OLLAMA_REPLICAS="${TEST_OLLAMA_REPLICAS:-unknown-replicas}"

TOTAL_REQUESTS="${1:-10}"
CONCURRENCY="${2:-10}"
SAVE_RESULT_LOG="${3:-0}"
RUN_TS="$(date +%Y%m%d-%H%M%S-%3N)"

mkdir -p results
OUT_FILE="results/results.jsonl"
METADATA_FILE="results/metadata.json"
GPU_METRICS_FILE="results/gpu-metrics.json"
RUN_RESULT_BASE="results/result-${RUN_TS}-${TEST_MIG_CONFIG}-replicas${TEST_OLLAMA_REPLICAS}-${NUM_PREDICT}"
RESULT_LOG="${RUN_RESULT_BASE}.log"
: > "$OUT_FILE"

if [[ "$SAVE_RESULT_LOG" == "1" || "$SAVE_RESULT_LOG" == "true" || "$SAVE_RESULT_LOG" == "yes" || "$SAVE_RESULT_LOG" == "on" ]]; then
  : > "$RESULT_LOG"
  exec > >(tee -a "$RESULT_LOG") 2>&1
fi

# Save metadata for the report. The workload timestamps are added after the run.
cat > "$METADATA_FILE" <<EOF
{
  "mig_config": "$TEST_MIG_CONFIG",
  "ollama_replicas": $TEST_OLLAMA_REPLICAS,
  "total_requests": $TOTAL_REQUESTS,
  "concurrency": $CONCURRENCY,
  "num_predict": $NUM_PREDICT,
  "run_timestamp": "$RUN_TS",
  "prometheus_url": "$PROMETHEUS_URL",
  "prometheus_step_seconds": $PROMETHEUS_STEP_SECONDS
}
EOF

ts() {
  date +"%H:%M:%S"
}

log() {
  printf '[%s] %s\n' "$(ts)" "$*"
}

log "Starting load test"
log "MIG Config: $TEST_MIG_CONFIG"
log "Ollama Replicas: $TEST_OLLAMA_REPLICAS"
log "Total requests: $TOTAL_REQUESTS"
log "Concurrency: $CONCURRENCY"
log "Output tokens (effort): $NUM_PREDICT"
log "Prometheus URL: $PROMETHEUS_URL"
log "Prometheus step: ${PROMETHEUS_STEP_SECONDS}s"

log "Checking required DCGM metrics"
if ! python3 collect_gpu_metrics.py \
  --prometheus-url "$PROMETHEUS_URL" \
  check; then
  log "ERROR: required GPU telemetry is unavailable; load test not started"
  exit 1
fi

run_request() {
  local id=$1

  start=$(date +%s%3N)

  response=$(curl -s -H "Connection: close" "$URL" -d "{
    \"model\": \"$MODEL\",
    \"prompt\": \"Write a very long and detailed explanation about distributed systems, Kubernetes scheduling, GPU partitioning with MIG, and performance tradeoffs. Include examples and technical depth.\",
    \"stream\": false,
    \"options\": {
      \"num_predict\": $NUM_PREDICT
    }
  }")

  end=$(date +%s%3N)

  echo "$response" | jq -c --arg start "$start" \
                         --arg end "$end" \
                         --arg num_predict "$NUM_PREDICT" \
  '{
    created_at,
    total_duration,
    load_duration,
    prompt_eval_count,
    prompt_eval_duration,
    eval_count,
    eval_duration,
    num_predict: ($num_predict|tonumber),
    start_time: ($start|tonumber),
    end_time: ($end|tonumber)
  }' >> "$OUT_FILE"

  log "REQUEST: $id - COMPLETED"
}

active_jobs=0
EXPERIMENT_START_S="$(date +%s.%N)"

for ((i=1; i<=TOTAL_REQUESTS; i++)); do
  run_request "$i" &

  ((active_jobs++))

  log "REQUEST: $i - STARTED in background (active_jobs=$active_jobs)"

  if ((active_jobs >= CONCURRENCY)); then
    log "WAITING -> active_jobs=$active_jobs"
    wait -n
    ((active_jobs--))
    log "RESUMING -> a request finished (active_jobs=$active_jobs)"
  fi
done

log "ALL REQUESTS LAUNCHED"
while ((active_jobs > 0)); do
  log "WAITING for remaining requests to finish (active_jobs=$active_jobs)"
  wait -n
  ((active_jobs--))
  log "REQUEST COMPLETED -> remaining active_jobs=$active_jobs"
done

EXPERIMENT_END_S="$(date +%s.%N)"
log "Load test completed"

METADATA_TMP="${METADATA_FILE}.tmp"
if jq \
  --argjson experiment_start_unix_s "$EXPERIMENT_START_S" \
  --argjson experiment_end_unix_s "$EXPERIMENT_END_S" \
  '. + {
    experiment_start_unix_s: $experiment_start_unix_s,
    experiment_end_unix_s: $experiment_end_unix_s
  }' \
  "$METADATA_FILE" > "$METADATA_TMP"; then
  mv "$METADATA_TMP" "$METADATA_FILE"
else
  rm -f "$METADATA_TMP"
  log "WARNING: could not add workload timestamps to metadata"
fi

log "Waiting ${PROMETHEUS_SCRAPE_WAIT_SECONDS}s for the final Prometheus scrape"
sleep "$PROMETHEUS_SCRAPE_WAIT_SECONDS"

gpu_collection_status=0
log "Collecting GPU telemetry from Prometheus"
if ! python3 collect_gpu_metrics.py \
  --prometheus-url "$PROMETHEUS_URL" \
  collect \
  --start "$EXPERIMENT_START_S" \
  --end "$EXPERIMENT_END_S" \
  --step "$PROMETHEUS_STEP_SECONDS" \
  --padding-before "$PROMETHEUS_PADDING_BEFORE_SECONDS" \
  --padding-after "$PROMETHEUS_PADDING_AFTER_SECONDS" \
  --output "$GPU_METRICS_FILE"; then
  gpu_collection_status=1
  log "ERROR: GPU telemetry collection failed; request analysis will still run"
fi

log "Running results evaluation"
SAVE_RESULT_LOG="$SAVE_RESULT_LOG" \
RESULT_LOG="$RESULT_LOG" \
RUN_RESULT_BASE="$RUN_RESULT_BASE" \
GPU_METRICS_FILE="$GPU_METRICS_FILE" \
python3 evaluate.py
evaluation_status=$?

if ((evaluation_status != 0)); then
  exit "$evaluation_status"
fi
exit "$gpu_collection_status"
