from __future__ import annotations
import argparse, ast, json, math, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P4_PROTOCOL='d482d03816e603544c4cd131ff3add0a078cd788'
EXPECTED={
 '.github/workflows/replaymark-runtime-gate-s2p4-minimal-transport-timer-execution.yml',
 'agentmark_e3b_lab/e3_mqtt/app/replaymark_s2p4_self_echo.py',
 'replaymark/S2P4_MINIMAL_TRANSPORT_TIMER_EXECUTION.md',
 'replaymark_verification/verify_s2p4_minimal_transport_timer_execution.py',
}
SCHEDULE=[[16,8,4],[8,4,16],[4,16,8]]
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def pct(xs,q):
 ys=sorted(xs); pos=(len(ys)-1)*q/100.; lo=math.floor(pos); hi=math.ceil(pos); return ys[lo] if lo==hi else ys[lo]*(hi-pos)+ys[hi]*(pos-lo)
def preflight():
 if git('rev-parse','HEAD^')!=P4_PROTOCOL:raise SystemExit('not exact P4 protocol child')
 if set(git('diff','--name-only',P4_PROTOCOL,'HEAD').splitlines())!=EXPECTED:raise SystemExit('undeclared P4 execution increment')
 p=json.loads((ROOT/'replaymark/S2P4_MINIMAL_TRANSPORT_TIMER_DISCRIMINATOR.json').read_text())
 assert p['status']=='FROZEN_AFTER_P3_MIXED_BEFORE_P4_EXECUTION_AND_BEFORE_ANY_TARGET_OUTCOME'
 src=(ROOT/'agentmark_e3b_lab/e3_mqtt/app/replaymark_s2p4_self_echo.py').read_text()
 tree=ast.parse(src); imports=[]
 for n in ast.walk(tree):
  if isinstance(n,ast.Import):imports += [a.name for a in n.names]
  elif isinstance(n,ast.ImportFrom) and n.module:imports.append(n.module)
 bad=[x for x in imports if x=='replaymark' or x.startswith('replaymark.') or x=='replaymark_oracle' or x.startswith('replaymark_oracle.')]
 if bad:raise SystemExit(f'semantic/oracle import leak {bad}')
 for token in ['set_state_delay(','-b/command','TCP_NODELAY, 1','setsockopt(']:
  if token in src:raise SystemExit(f'forbidden execution token {token}')
 return {'exact_p4_protocol_parent':True,'declared_files_only':True,'runner_semantic_oracle_imports':0,'socket_options_modified':False,'target_path_absent':True}
def verify(round_paths):
 rows=[]; round_checks=[]; delayed=[]; nodelays=[]
 for ri,path in enumerate(round_paths):
  d=json.loads(Path(path).read_text()); ok=d.get('schema')=='replaymark.s2p4-self-echo-round.v1' and d.get('round_index')==ri and d.get('frozen_order')==SCHEDULE[ri] and d.get('broker')=='mosquitto version 2.1.2' and d.get('paho_version')=='2.1.0' and d.get('source_only') is True and d.get('device_service_started') is False and len(d.get('cells',[]))==3
  nodelays.append(d.get('tcp_nodelay_value'))
  for pos,c in enumerate(d.get('cells',[])):
   ok=ok and c.get('position')==pos and c.get('wave_size')==SCHEDULE[ri][pos] and len(c.get('rows',[]))==192
   delayed.append(c.get('tcp_delayed_acks_delta'))
   for tid,r in enumerate(c.get('rows',[])):
    ok=ok and r.get('task_id')==tid and r.get('completed') is True and r.get('echo_recv_mono_ns') is not None
    rows.append(r)
  round_checks.append(ok)
 if len(rows)!=1728 or not all(round_checks):raise SystemExit('invalid P4 rows')
 echo=[float(r['self_echo_receive_latency_ms']) for r in rows]; ack=[float(r['puback_latency_ms']) for r in rows]
 def stats(xs):
  return {'p50':pct(xs,50),'p95':pct(xs,95),'p99':pct(xs,99),'max':max(xs),'fraction_35_45':sum(35<=x<=45 for x in xs)/len(xs),'fraction_gt_30':sum(x>30 for x in xs)/len(xs)}
 es,as_=stats(echo),stats(ack)
 reproduced=(es['fraction_35_45']>=.10 and es['p95']>=35) or (as_['fraction_35_45']>=.10 and as_['p95']>=35)
 clean=es['p99']<20 and as_['p99']<20 and es['fraction_gt_30']<.01 and as_['fraction_gt_30']<.01
 cls='SELF_ECHO_REPRODUCES_40MS_STRUCTURE' if reproduced else ('SELF_ECHO_CLEAN' if clean else 'AMBIGUOUS')
 return {'scientific_verdict':'PASS','classification':cls,'rows':len(rows),'echo':es,'puback':as_,'tcp_nodelay_values':nodelays,'TcpExtDelayedACKs_deltas':delayed,'shifted_target_executed':False,'device_service_started':False,'W_star':None,'D_star':None}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--preflight-only',action='store_true'); ap.add_argument('--round',action='append',default=[]); ap.add_argument('--out',required=True); args=ap.parse_args()
 report={'schema':'replaymark.s2p4-minimal-transport-timer-verification.v1','preflight':preflight(),'verdict':'PASS'}
 if not args.preflight_only:
  if len(args.round)!=3:raise SystemExit('need three rounds')
  report['scientific']=verify(args.round)
 Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
