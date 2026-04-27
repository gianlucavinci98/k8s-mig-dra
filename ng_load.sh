#!/bin/bash

URL="http://10.146.0.55:31134/api/generate"
MODEL="tinyllama"

TOTAL_REQUESTS="${1:-20}"
CONCURRENCY="${2:-5}"
RUN_TS="$(date +%Y%m%d-%H%M%S-%3N)"

OUT_FILE="results.jsonl"
: > "$OUT_FILE"
RESULT_LOG="result-${RUN_TS}.log"
: > "$RESULT_LOG"
exec > >(tee -a "$RESULT_LOG") 2>&1

ts() {
  date +"%H:%M:%S"
}

log() {
  printf '[%s] %s\n' "$(ts)" "$*"
}

log "Starting load test"
log "Total requests: $TOTAL_REQUESTS"
log "Concurrency: $CONCURRENCY"

run_request() {
  local id=$1

  start=$(date +%s%3N)

  response=$(curl -s -H "Connection: close" "$URL" -d "{
    \"model\": \"$MODEL\",
    \"prompt\": \"Write a very long and detailed explanation about distributed systems, Kubernetes scheduling, GPU partitioning with MIG, and performance tradeoffs. Include examples and technical depth.\",
    \"stream\": false,
    \"options\": {
      \"num_predict\": 400
    }
  }")

  end=$(date +%s%3N)

  echo "$response" | jq -c --arg start "$start" \
                         --arg end "$end" \
  '{
    created_at,
    total_duration,
    load_duration,
    prompt_eval_count,
    prompt_eval_duration,
    eval_count,
    eval_duration,
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
python3 evaluate.py