#!/bin/bash

URL="http://10.146.0.55:31134/api/generate"
MODEL="tinyllama"

TOTAL_REQUESTS=20
CONCURRENCY=5

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
      \"temperature\": 0.7
    }
  }" > /dev/null
}

active_jobs=0

for ((i=1; i<=TOTAL_REQUESTS; i++)); do
  log "Launching request $i (active_jobs=$active_jobs)"
  run_request &

  ((active_jobs++))
  log "Request $i started in background (active_jobs=$active_jobs)"

  if ((active_jobs >= CONCURRENCY)); then
    log "Waiting because active_jobs=$active_jobs reached the concurrency limit ($CONCURRENCY)"
    wait -n
    ((active_jobs--))
    log "A request finished, resuming (active_jobs=$active_jobs)"
  fi
done

while ((active_jobs > 0)); do
  log "Waiting for remaining requests to finish (active_jobs=$active_jobs)"
  wait -n
  ((active_jobs--))
  log "A request finished, remaining active_jobs=$active_jobs"
done

log "Load test completed"