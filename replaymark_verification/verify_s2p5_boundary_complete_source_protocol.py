from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P4_RESULT='dce36dc9303bb6c31b074ea48ac79f5a76ea891b'
EXPECTED={
 '.github/workflows/replaymark-runtime-gate-s2p5-boundary-complete-source-protocol.yml',
 'replaymark/S2P5_BOUNDARY_COMPLETE_SOURCE_QUALIFICATION.json',
 'replaymark/S2P5_BOUNDARY_COMPLETE_SOURCE_QUALIFICATION.md',
 'replaymark_verification/verify_s2p5_boundary_complete_source_protocol.py',
}
RUNNER='agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q2_source_load_envelope.py'
RUNNER_BLOB='c263486aaf2d7dde05dd557e22a2324024c7575e'
OBS='replaymark/runtime_e3b_observation.py'; OBS_BLOB='de6cdc8ccdbb9b189e238cc5dbad173060fe17ab'
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); args=ap.parse_args()
 if git('rev-parse','HEAD^')!=P4_RESULT:raise SystemExit('P5 must be exact child of P4 result seal')
 changed=set(git('diff','--name-only',P4_RESULT,'HEAD').splitlines())
 if changed!=EXPECTED:raise SystemExit(f'undeclared P5 increment: {sorted(changed)}')
 p=json.loads((ROOT/'replaymark/S2P5_BOUNDARY_COMPLETE_SOURCE_QUALIFICATION.json').read_text())
 assert p['status']=='FROZEN_AFTER_P4_BEFORE_FRESH_P5_SOURCE_OR_ANY_SHIFTED_TARGET_OUTCOME'
 assert p['measurement_reuse']['new_source_runner_allowed'] is False
 assert git('rev-parse',f'HEAD:{RUNNER}')==RUNNER_BLOB
 assert git('rev-parse',f'HEAD:{OBS}')==OBS_BLOB
 assert p['inheritance']['candidate_waves']==[16,8,4]
 assert p['inheritance']['screening_schedule']==[[16,8,4],[8,4,16],[4,16,8]]
 assert p['inheritance']['verify_deadline_ms']==100.0
 assert p['boundary_complete_source_qualification']['old_80ms_p99_rule']=='REMOVED_FROM_PROMOTION_IN_THIS_NEW_PROTOCOL_GENERATION_AND_REPORTED_DESCRIPTIVELY_ONLY'
 assert 'p99' in ' '.join(p['boundary_complete_source_qualification']['descriptive_only_metrics'])
 assert all(p['anti_fishing'].values())
 assert p['dstar_seal']['definition']=='D_star_ms = floor((100.0 - pooled_median_holdout_completion_ms) + 0.5)'
 assert p['fresh_holdout']['replicates']==3 and p['fresh_holdout']['rows']==576
 # Semantic anchoring: exact frozen rule record must require closure at/after deadline and inclusive receive interval.
 obs=(ROOT/OBS).read_text()
 for token in ['closed_at_mono_ns_must_be_at_or_after_deadline','command_publish_mono_ns <= event.recv_mono_ns','<= verify_deadline_mono_ns','deadline_inclusive']:
  if token not in obs:raise SystemExit(f'frozen observation semantic anchor missing: {token}')
 wf=(ROOT/'.github/workflows/replaymark-runtime-gate-s2p5-boundary-complete-source-protocol.yml').read_text().lower()
 for token in ['docker compose up','runner_shadow','set_state_delay(','--mode screening-round']:
  if token in wf:raise SystemExit(f'P5 protocol workflow executes source/target: {token}')
 report={
  'schema':'replaymark.s2p5-boundary-complete-source-protocol-freeze.v1','verdict':'PASS','exact_p4_result_parent':True,
  'declared_files_only':True,'frozen_q2_source_runner_reused':True,'frozen_observation_realizer_anchored':True,
  'candidate_waves':[16,8,4],'verify_deadline_ms':100.0,'p99_promotion_role':'NONE_DESCRIPTIVE_ONLY',
  'fresh_source_executed':False,'target_executed':False,'W_star':None,'D_star':None,
  'protocol_sha256':hashlib.sha256((ROOT/'replaymark/S2P5_BOUNDARY_COMPLETE_SOURCE_QUALIFICATION.json').read_bytes()).hexdigest(),
  'next_gate':'S2Q3_BOUNDARY_COMPLETE_SOURCE_SCREEN_HOLDOUT_AND_DSTAR_SEAL'}
 out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
