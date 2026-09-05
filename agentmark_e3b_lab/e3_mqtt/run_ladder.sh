#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
rm -f results/e3b_r0_r1_r2_certificate.json
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose up -d --build mosquitto device
cleanup() { docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker compose run --rm runner_ladder
python - <<'PY'
import json
d=json.load(open('results/e3b_r0_r1_r2_certificate.json'))
assert d['schema']=='agentmark.e3b.r0_r1_r2_certificate.v1'
assert d['broker_version_sys']
assert d['replay_safety_certificate']['classification'] != 'CERTIFIED_SAFE'
assert d['recorded_act2_under_timeout_compatibility']['support_failures'] == 1
assert all(d['promotion_checks'].values()), d['promotion_checks']
assert d['promotion_pass'] is True
print(json.dumps({'gate':d['gate'],'broker_version_sys':d['broker_version_sys'],'certificate':d['replay_safety_certificate']['classification'],'promotion_pass':d['promotion_pass'],'aggregate':d['aggregate']},indent=2,sort_keys=True))
PY
