#!/usr/bin/env bash
set -euo pipefail
replica="${1:?replica id required}"
cd "$(dirname "$0")"
mkdir -p results
rm -f "results/replica-${replica}.json"
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
cleanup(){ docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker compose up -d --build mosquitto device
docker compose run --rm runner \
  python /app/audit/barrier_wrapper.py \
  --broker mosquitto \
  --replica "$replica" \
  --verify-ms 100 \
  --delays-ms 80,95 \
  --blocks 8 \
  --tasks 128 \
  --wave-size 32 \
  --wave-period-ms 300 \
  --gap-ms 20 \
  --timeout-ms 1200 \
  --serial-tasks 20 \
  --serial-period-ms 300 \
  --out "/results/replica-${replica}.json"
test -s "results/replica-${replica}.json"
