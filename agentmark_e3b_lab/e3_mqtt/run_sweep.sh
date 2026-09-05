#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p results; rm -f results/e3b_replay_safety_sweep.json
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose up -d --build mosquitto device
cleanup(){ docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }; trap cleanup EXIT
docker compose run --rm runner_sweep
python - <<'PY'
import json
d=json.load(open('results/e3b_replay_safety_sweep.json'))
assert d['schema']=='agentmark.e3b.replay_safety_sweep.v1'
assert d['broker_version_sys']=='mosquitto version 2.1.2'
assert all(d['checks'].values()), d['checks']
print(json.dumps({'broker':d['broker_version_sys'],'verify_ms':d['parameters']['calibrated_verify_ms'],'points':[{'offset_ms':x['offset_ms'],'target_miss_rate':x['target_miss_rate'],'classification':x['certificate']['classification'],'r1_violation':x['r1_support_violation_fraction_mean'],'r2_verify':x['r2_verify_fraction_mean'],'publish_ratio':x['r2_broker_publish_over_r1_mean']} for x in d['points']]},indent=2,sort_keys=True))
PY
