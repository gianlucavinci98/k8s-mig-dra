#!/bin/bash

URL="http://10.146.0.55:31134/api/generate"
MODEL="tinyllama"

TOTAL_REQUESTS="${1:-20}"
CONCURRENCY="${2:-5}"

OUT_FILE="results.jsonl"
: > "$OUT_FILE"

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

  latency=$((end - start))

  echo "$response" | jq -c --arg start "$start" \
                         --arg end "$end" \
                         --arg latency "$latency" \
  '{
    created_at,
    total_duration,
    load_duration,
    prompt_eval_count,
    prompt_eval_duration,
    eval_count,
    eval_duration,
    start_time: ($start|tonumber),
    end_time: ($end|tonumber),
    latency_ms: ($latency|tonumber)
  }' >> "$OUT_FILE"
}

active_jobs=0

for ((i=1; i<=TOTAL_REQUESTS; i++)); do
  run_request $i &

  ((active_jobs++))

  if ((active_jobs >= CONCURRENCY)); then
    wait -n
    ((active_jobs--))
  fi
done

wait