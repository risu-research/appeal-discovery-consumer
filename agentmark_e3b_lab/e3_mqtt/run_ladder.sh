#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p results; rm -f results/e3b_r0_r1_r2_certificate.json
docker compose down -v --remove-orphans >/dev/null 2>&1 || true
docker compose up -d --build mosquitto device
cleanup(){ docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }; trap cleanup EXIT
docker compose run --rm runner_ladder
python - <<'PY'
import json
d=json.load(open('results/e3b_r0_r1_r2_certificate.json'))
assert d['schema']=='agentmark.e3b.r0_r1_r2_certificate.v2'
assert d['broker_version_sys']=='mosquitto version 2.1.2'
assert d['replay_safety_certificate']['classification']=='CERTIFIED_UNSAFE'
assert d['recorded_act2_under_changed_feedback']['support_failures']==1
assert d['promotion_checks']['broker_publish_conservation_exact'] is True
assert d['promotion_pass'] is True, d['promotion_checks']
print(json.dumps({'gate':d['gate'],'broker':d['broker_version_sys'],'promotion_pass':d['promotion_pass'],'certificate':d['replay_safety_certificate']['classification'],'aggregate':d['aggregate']},indent=2,sort_keys=True))
PY
