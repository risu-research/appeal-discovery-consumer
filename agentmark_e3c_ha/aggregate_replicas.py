from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('results', nargs='+')
    ap.add_argument('--validations', nargs='+', required=True)
    ap.add_argument('--image-ref-file', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    result_paths = [Path(x) for x in args.results]
    validation_paths = [Path(x) for x in args.validations]
    results = [load(p) for p in result_paths]
    validations = [load(p) for p in validation_paths]
    image_ref = Path(args.image_ref_file).read_text(encoding='utf-8').strip()

    if len(results) < 2:
        raise AssertionError('replicated E3c requires >=2 independent runner results')
    if len(results) != len(validations):
        raise AssertionError('result/validation count mismatch')
    if not all(v['pass'] for v in validations):
        raise AssertionError('an independent replica validation failed')
    if not all(r['decision'] == 'PROMOTED' for r in results):
        raise AssertionError('an E3c replica failed promotion')
    if len({r['environment']['home_assistant_core_version'] for r in results}) != 1:
        raise AssertionError('Home Assistant versions differ across replicas')

    total_trials = sum(int(r['frozen_protocol']['trials']) for r in results)
    tasks = int(results[0]['frozen_protocol']['tasks'])
    trial_call_counts = []
    combined_rows = {m: [] for m in ('R0','R1','R2')}
    source_p99 = []
    source_max = []
    for r in results:
        source_p99.append(float(r['source']['act1_complete_p99_ms']))
        source_max.append(float(r['source']['act1_complete_max_ms']))
        for tkey, modes in r['raw_replay_rows']['decisive'].items():
            rec = {'replica': r['replica'], 'trial': int(tkey)}
            for m in ('R0','R1','R2'):
                rows = modes[m]
                combined_rows[m].extend(rows)
                rec[m] = 2 * len(rows) + sum(bool(x['verify_called']) for x in rows)
            if rec['R0'] != 2*tasks or rec['R1'] != 2*tasks or rec['R2'] != 3*tasks:
                raise AssertionError(f'cross-replica conservation failed: {rec}')
            trial_call_counts.append(rec)

    def rates(rows):
        n = len(rows)
        return {
            'n': n,
            'miss_rate': sum(x['feedback_at_deadline']=='MISS' for x in rows)/n,
            'support_violation_rate': sum(bool(x['support_violation']) for x in rows)/n,
            'verify_fraction': sum(bool(x['verify_called']) for x in rows)/n,
            'mean_act2_shift_vs_source_ms': statistics.fmean(float(x['act2_issue_shift_vs_source_ms']) for x in rows),
        }

    aggregate = {m: rates(rows) for m, rows in combined_rows.items()}
    if aggregate['R0']['support_violation_rate'] != 1.0:
        raise AssertionError('combined R0 support failure is not 100%')
    if aggregate['R1']['support_violation_rate'] != 1.0:
        raise AssertionError('combined R1 support failure is not 100%')
    if aggregate['R2']['support_violation_rate'] != 0.0 or aggregate['R2']['verify_fraction'] != 1.0:
        raise AssertionError('combined R2 semantic preservation failed')

    report = {
        'schema': 'agentmark.e3c.home_assistant.replicated_aggregate.v1',
        'decision': 'PROMOTED_REPLICATED',
        'replicas': len(results),
        'total_decisive_trials': total_trials,
        'tasks_per_trial': tasks,
        'home_assistant_core_version': results[0]['environment']['home_assistant_core_version'],
        'home_assistant_image_ref': image_ref,
        'source_completion_p99_ms_by_replica': source_p99,
        'source_completion_max_ms_by_replica': source_max,
        'aggregate': aggregate,
        'exact_native_work_per_trial': {'R0':2*tasks, 'R1':2*tasks, 'R2':3*tasks, 'R2_over_R1':1.5},
        'trial_call_counts': trial_call_counts,
        'controls': {
            'all_no_shift_controls_pass': all(r['promotion_gates']['no_shift_negative_control'] for r in results),
            'all_feedback_insensitive_controls_pass': all(r['promotion_gates']['feedback_insensitive_negative_control'] for r in results),
        },
        'input_artifacts': [
            {'path': str(p), 'sha256': sha256(p), 'replica': r.get('replica')}
            for p, r in zip(result_paths, results)
        ],
        'validation_artifacts': [
            {'path': str(p), 'sha256': sha256(p), 'pass': v['pass'], 'replica': v.get('replica')}
            for p, v in zip(validation_paths, validations)
        ],
        'claim_boundary': (
            'This promotes ecological replication on Home Assistant Core middleware semantics. '
            'The device is still a deterministic virtual device; E3c does not claim physical-device or radio-layer validation.'
        ),
    }
    if not all(report['controls'].values()):
        raise AssertionError('a negative control failed across replicas')
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
