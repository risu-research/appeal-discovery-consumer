from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P3_SEAL='cbd39120e875aa6773c931c4f7aaa023835199a2'
EXPECTED={
 '.github/workflows/replaymark-runtime-gate-s2p4-minimal-transport-timer-protocol.yml',
 'replaymark/S2P4_MINIMAL_TRANSPORT_TIMER_DISCRIMINATOR.json',
 'replaymark/S2P4_MINIMAL_TRANSPORT_TIMER_DISCRIMINATOR.md',
 'replaymark_verification/verify_s2p4_minimal_transport_timer_protocol.py',
}
def git(*a:str)->str:return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); args=ap.parse_args()
 parent=git('rev-parse','HEAD^')
 if parent!=P3_SEAL: raise SystemExit(f'P4 must be exact child of P3 result seal: {parent}')
 changed=set(git('diff','--name-only',P3_SEAL,'HEAD').splitlines())
 if changed!=EXPECTED: raise SystemExit(f'undeclared P4 increment: {sorted(changed)}')
 p=json.loads((ROOT/'replaymark/S2P4_MINIMAL_TRANSPORT_TIMER_DISCRIMINATOR.json').read_text())
 assert p['status']=='FROZEN_AFTER_P3_MIXED_BEFORE_P4_EXECUTION_AND_BEFORE_ANY_TARGET_OUTCOME'
 assert p['execution']['device_service_started'] is False
 assert p['execution']['shifted_target_executed'] is False
 assert p['execution']['act2_candidate_constructed'] is False
 assert p['execution']['single_paho_connection'] is True
 assert p['execution']['qos']==1 and p['execution']['rounds']==3 and p['execution']['tasks_per_cell']==192 and p['execution']['total_rows']==1728
 assert p['execution']['schedule']==[[16,8,4],[8,4,16],[4,16,8]]
 assert p['kernel_timer_candidate']['candidate_quantum_ms']==40.0
 assert p['kernel_timer_candidate']['quantized_window_ms']==[35.0,45.0]
 assert all(p['anti_fishing'].values())
 seal=json.loads((ROOT/'replaymark/S2P3_EMBEDDED_TAIL_LOCALIZATION_RESULT_SEAL.json').read_text())
 assert seal['execution_head']=='8378113f4392a69c282f402fe3ef4fd0c93738f3'
 assert seal['scientific']['classification']=='MIXED_OR_UNLOCALIZED'
 runtime=json.loads((ROOT/'replaymark/CURRENT_RUNTIME_SEAL.json').read_text())
 assert runtime['optimization_policy']['state']=='FROZEN'
 assert git('rev-parse','HEAD:agentmark_e3b_lab/e3_mqtt/app/device.py')=='27240e65cb8e1a7d788cc5dea8484cbad8ec6653'
 assert git('rev-parse','HEAD:agentmark_e3b_lab/e3_mqtt/app/experiment.py')=='a5c7483b198bc03f251d31b75750c27fad1f2d29'
 wf=(ROOT/'.github/workflows/replaymark-runtime-gate-s2p4-minimal-transport-timer-protocol.yml').read_text().lower()
 for token in ['docker compose up','runner_shadow','mosquitto_sub','set_state_delay(']:
  if token in wf: raise SystemExit(f'protocol workflow executes live diagnostic: {token}')
 report={
  'schema':'replaymark.s2p4-minimal-transport-timer-protocol-freeze.v1','verdict':'PASS','exact_p3_result_seal_parent':True,
  'declared_files_only':True,'protocol_sha256':hashlib.sha256((ROOT/'replaymark/S2P4_MINIMAL_TRANSPORT_TIMER_DISCRIMINATOR.json').read_bytes()).hexdigest(),
  'device_frozen':True,'experiment_frozen':True,'target_executed':False,'device_service_started':False,'W_star':None,'D_star':None,
  'next_gate':'S2P4E_MINIMAL_TRANSPORT_TIMER_DISCRIMINATOR_EXECUTION'}
 out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
