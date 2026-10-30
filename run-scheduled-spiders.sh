#!/usr/bin/env bash
set -Eeuo pipefail

# Run every registered spider immediately, then wait a random 2-4 hours.
# 7200 seconds = 2 hours; 14400 seconds = 4 hours.
while true; do
  echo "[$(date -Is)] starting scheduled crawl"
  /app/run-all-spiders.sh
  echo "[$(date -Is)] scheduled crawl finished"

  delay=$((7200 + RANDOM % 7201))
  echo "[$(date -Is)] next crawl in ${delay} seconds"
  sleep "$delay"
done
