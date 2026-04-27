#!/bin/bash

URL="http://10.146.0.55:31134/api/generate"
MODEL="tinyllama"

TOTAL_REQUESTS="${1:-20}"
CONCURRENCY="${2:-5}"
RESULT_LOG="result.log"

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
  curl -s -H "Connection: close" "$URL" -d "{
    \"model\": \"$MODEL\",
    \"prompt\": \"Write a very long and detailed explanation about distributed systems, Kubernetes scheduling, GPU partitioning with MIG, and performance tradeoffs. Include examples and technical depth.\",
    \"stream\": false,
    \"options\": {
      \"num_predict\": 512,
      \"temperature\": 0.7,
    }
  }" > /dev/null
}

active_jobs=0

for ((i=1; i<=TOTAL_REQUESTS; i++)); do
  log "REQUEST: $i - LAUNCHING\t(active_jobs=$active_jobs)"
  run_request &

  ((active_jobs++))
  log "REQUEST: $i - STARTED in background\t(active_jobs=$active_jobs)"

  if ((active_jobs >= CONCURRENCY)); then
    log "WAITING -> active_jobs=$active_jobs reached the concurrency limit ($CONCURRENCY)"
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