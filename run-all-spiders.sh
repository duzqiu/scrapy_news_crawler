#!/usr/bin/env bash
set -Eeuo pipefail

mapfile -t spiders < <(scrapy list)

if ((${#spiders[@]} == 0)); then
  echo "No Scrapy spiders found" >&2
  exit 1
fi

for spider in "${spiders[@]}"; do
  echo "[$(date -Is)] starting spider: ${spider}"
  scrapy crawl "$spider"
  echo "[$(date -Is)] finished spider: ${spider}"
done
