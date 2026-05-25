#!/bin/bash

URL="http://10.146.0.55:31134/api/generate"
MODEL="tinyllama"
NUM_PREDICT="${NUM_PREDICT:-500}"

TEST_MIG_CONFIG="$(kubectl get nodes -o json | jq -r '.items[].metadata.labels["nvidia.com/mig.config"] // empty' | awk 'NF { print; exit }')"
TEST_OLLAMA_REPLICAS="$(kubectl -n ollama-test get deploy ollama-mig -o jsonpath='{.spec.replicas}' 2>/dev/null)"

TEST_MIG_CONFIG="${TEST_MIG_CONFIG:-unknown-mig-config}"
TEST_OLLAMA_REPLICAS="${TEST_OLLAMA_REPLICAS:-unknown-replicas}"

TOTAL_REQUESTS="${1:-10}"
CONCURRENCY="${2:-10}"
SAVE_RESULT_LOG="${3:-0}"
RUN_TS="$(date +%Y%m%d-%H%M%S-%3N)"

OUT_FILE="results/results.jsonl"
METADATA_FILE="results/metadata.json"
: > "$OUT_FILE"
RESULT_LOG="results/result-${RUN_TS}-${TEST_MIG_CONFIG}-replicas${TEST_OLLAMA_REPLICAS}-${NUM_PREDICT}.log"

if [[ "$SAVE_RESULT_LOG" == "1" || "$SAVE_RESULT_LOG" == "true" || "$SAVE_RESULT_LOG" == "yes" || "$SAVE_RESULT_LOG" == "on" ]]; then
  : > "$RESULT_LOG"
  exec > >(tee -a "$RESULT_LOG") 2>&1
fi

# Save metadata for the report
cat > "$METADATA_FILE" <<EOF
{
  "mig_config": "$TEST_MIG_CONFIG",
  "ollama_replicas": $TEST_OLLAMA_REPLICAS,
  "total_requests": $TOTAL_REQUESTS,
  "concurrency": $CONCURRENCY,
  "num_predict": $NUM_PREDICT
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

for ((i=1; i<=TOTAL_REQUESTS; i++)); do
  run_request $i &

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

log "Load test completed"

log "Running results evaluation"
SAVE_RESULT_LOG="$SAVE_RESULT_LOG" python3 evaluate.py