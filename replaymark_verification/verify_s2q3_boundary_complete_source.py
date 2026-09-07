from __future__ import annotations
import argparse, hashlib, json, math, statistics, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P5='a21192a7214c2e8eb6d2a4940775172a65b3e1e8'
RUNNER='agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q2_source_load_envelope.py'
RUNNER_BLOB='c263486aaf2d7dde05dd557e22a2324024c7575e'
EXPECTED={
 '.github/workflows/replaymark-runtime-gate-s2q3-boundary-complete-source.yml',
 'replaymark/S2Q3_BOUNDARY_COMPLETE_SOURCE_EXECUTION.md',
 'replaymark_verification/verify_s2q3_boundary_complete_source.py',
}
SCHEDULE=((16,8,4),(8,4,16),(4,16,8)); WAVES=(16,8,4); TASKS=192; VERIFY=100.0; TIMEOUT=1000; PERIOD=300.0
SEAL_SCHEMA='replaymark.s2q2-screening-selection-seal.v1'
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pct(xs,q):
 ys=sorted(xs)
 if not ys:return None
 pos=(len(ys)-1)*q/100.; lo=math.floor(pos); hi=math.ceil(pos)
 return ys[lo] if lo==hi else ys[lo]*(hi-pos)+ys[hi]*(pos-lo)
def eq(a,b,tol=1e-9):
 if a is None or b is None:return a is None and b is None
 return abs(float(a)-float(b))<=tol

def preflight():
 if git('rev-parse','HEAD^')!=P5:raise SystemExit('Q3 must be exact child of P5')
 if set(git('diff','--name-only',P5,'HEAD').splitlines())!=EXPECTED:raise SystemExit('undeclared Q3 increment')
 if git('rev-parse',f'HEAD:{RUNNER}')!=RUNNER_BLOB:raise SystemExit('frozen Q2 source runner drift')
 p=json.loads((ROOT/'replaymark/S2P5_BOUNDARY_COMPLETE_SOURCE_QUALIFICATION.json').read_text())
 assert p['status']=='FROZEN_AFTER_P4_BEFORE_FRESH_P5_SOURCE_OR_ANY_SHIFTED_TARGET_OUTCOME'
 wf=(ROOT/'.github/workflows/replaymark-runtime-gate-s2q3-boundary-complete-source.yml').read_text()
 if wf.count('--mode screening-round')!=3 or wf.count('--mode holdout')!=3:raise SystemExit('Q3 workflow invocation count drift')
 for i in range(3):
  if wf.count(f'--round-index {i}')!=1 or wf.count(f'--holdout-replicate {i}')!=1:raise SystemExit('Q3 index invocation drift')
 for bad in ['replaymark_s2_admission_live','-b/command','set_state_delay(']:
  if bad in wf:raise SystemExit(f'target token in Q3 workflow: {bad}')
 return {'exact_p5_parent':True,'declared_files_only':True,'frozen_source_runner_reused':True,'target_path_absent':True,'p99_promotion_role':'NONE'}

def validate_cell(cell,phase,rep,round_index,position,wave):
 if not isinstance(cell,dict):return {'valid':False,'rows':[],'offsets':[],'lateness':[],'prefix':None}
 rows=cell.get('rows'); prefix=cell.get('prefix'); ok=cell.get('phase')==phase and cell.get('replicate')==rep and cell.get('round_index')==round_index and cell.get('position')==position and cell.get('wave_size')==wave and isinstance(rows,list) and len(rows)==TASKS and isinstance(prefix,str)
 offsets=[]; late=[]; base=None; out=[]
 if not isinstance(rows,list) or not isinstance(prefix,str):return {'valid':False,'rows':[],'offsets':[],'lateness':[],'prefix':prefix}
 for tid,r in enumerate(rows):
  out.append(r)
  try:
   offer=int(r['offer_mono_ns']); t0=int(r['task_start_mono_ns']); pub=int(r['act1_publish_mono_ns']); vd=int(r['verify_deadline_mono_ns']); td=int(r['task_timeout_deadline_mono_ns']); recv=None if r['state_on_recv_mono_ns'] is None else int(r['state_on_recv_mono_ns'])
   if base is None:base=offer
   expected_offer=base+(tid//wave)*int(PERIOD*1e6); comp=None if recv is None else (recv-t0)/1e6; lat=(t0-offer)/1e6
   vis=recv is not None and pub<=recv<=vd; complete=recv is not None and pub<=recv<=td
   rowok=r.get('phase')==phase and r.get('replicate')==rep and r.get('round_index')==round_index and r.get('position')==position and r.get('wave_size')==wave and r.get('task_id')==tid and r.get('device')==f'{prefix}-{tid}-a' and r.get('state_delay_ms')==0 and offer==expected_offer and t0>=offer and pub>=t0 and vd==t0+int(VERIFY*1e6) and td==t0+int(TIMEOUT*1e6) and eq(r.get('completion_offset_ms'),comp) and eq(r.get('start_lateness_ms'),lat) and r.get('visible_by_verify_deadline') is vis and r.get('completed_by_task_timeout') is complete
   if recv is None: rowok=rowok and r.get('event_on') is None and r.get('event_device') is None and r.get('event_cause') is None
   else:
    rowok=rowok and r.get('event_on') is True and r.get('event_device')==f'{prefix}-{tid}-a' and r.get('event_cause')=='command'; offsets.append(float(comp))
   late.append(float(lat)); ok=ok and rowok
  except Exception: ok=False
 preview=cell.get('runner_descriptive_preview',{}); p99=pct(offsets,99)
 ok=ok and preview.get('row_count')==len(out) and preview.get('completion_count')==len(offsets) and preview.get('visible_by_verify_deadline')==sum(bool(r.get('visible_by_verify_deadline')) for r in out) and eq(preview.get('completion_median_ms'),statistics.median(offsets) if offsets else None) and eq(preview.get('completion_p99_ms'),p99) and eq(preview.get('start_lateness_p99_ms'),pct(late,99))
 return {'valid':bool(ok),'rows':out,'offsets':offsets,'lateness':late,'prefix':prefix,'p99_ms':p99}

def screening(screen_dir):
 candidate={w:[] for w in WAVES}; prefixes=[]; hashes={}; round_ok=[]
 for ri in range(3):
  path=Path(screen_dir)/f'q3_screen_round_{ri}.json'; d=json.loads(path.read_text()); hashes[f'round_{ri}']=sha(path)
  order=list(SCHEDULE[ri]); ok=d.get('schema')=='replaymark.s2q2-source-screening-round.v1' and d.get('source_only') is True and d.get('shifted_target_executed') is False and d.get('act2_candidate_constructed') is False and d.get('broker')=='mosquitto version 2.1.2' and d.get('state_delay_ms')==0 and d.get('round_index')==ri and d.get('frozen_order')==order
  cells=d.get('cells',[]); ok=ok and isinstance(cells,list) and len(cells)==3
  for pos,w in enumerate(order):
   v=validate_cell(cells[pos] if pos<len(cells) else None,'screening',ri,ri,pos,w); ok=ok and v['valid']; candidate[w].append(v)
   if isinstance(v['prefix'],str):prefixes.append(v['prefix'])
  round_ok.append(ok)
 stats={}; passing=[]
 for w in WAVES:
  vs=candidate[w]; rows=[r for v in vs for r in v['rows']]; offs=[x for v in vs for x in v['offsets']]; lates=[x for v in vs for x in v['lateness']]
  structural=len(vs)==3 and all(v['valid'] for v in vs); complete=len(rows)==576 and len(offs)==576 and all(r.get('completed_by_task_timeout') is True for r in rows); visible=len(rows)==576 and all(r.get('visible_by_verify_deadline') is True for r in rows)
  qualifies=structural and complete and visible
  if qualifies:passing.append(w)
  stats[str(w)]={'rows':len(rows),'all_rows_structurally_valid':structural,'all_tasks_complete_by_timeout':complete,'all_tasks_visible_by_verify_deadline':visible,'visible_count':sum(bool(r.get('visible_by_verify_deadline')) for r in rows),'completion_p50_ms':pct(offs,50),'completion_p95_ms':pct(offs,95),'completion_p99_ms':pct(offs,99),'completion_max_ms':max(offs) if offs else None,'start_lateness_p99_ms':pct(lates,99),'qualifies':qualifies,'p99_role':'DESCRIPTIVE_ONLY'}
 all_round=all(round_ok); fresh=len(prefixes)==9 and len(set(prefixes))==9; w=max(passing) if passing and all_round and fresh else None
 return {'screening_verdict':'PASS' if w is not None else 'FAIL','W_star_screen':w,'candidate_stats':stats,'screening_result_sha256s':hashes,'all_rounds_structurally_valid':all_round,'all_candidate_namespaces_fresh':fresh,'source_rows':sum(v['rows'] for v in stats.values())}

def make_seal(s):
 p=ROOT/'replaymark/S2P5_BOUNDARY_COMPLETE_SOURCE_QUALIFICATION.json'
 return {'schema':SEAL_SCHEMA,'screening_verdict':s['screening_verdict'],'W_star_screen':s['W_star_screen'],'q3_execution_head':git('rev-parse','HEAD'),'p5_head':P5,'p5_protocol_sha256':sha(p),'selection_basis':'BOUNDARY_COMPLETE_BY_100MS','candidate_stats':s['candidate_stats'],'screening_result_sha256s':s['screening_result_sha256s'],'p99_promotion_role':'NONE_DESCRIPTIVE_ONLY'}

def holdout(hold_dir,seal_path):
 seal=json.loads(Path(seal_path).read_text()); w=seal.get('W_star_screen')
 if seal.get('screening_verdict')!='PASS' or w not in WAVES:return {'holdout_admitted':False,'holdout_verdict':'NOT_ADMITTED','rows':0,'D_star_ms':None}
 prefixes=[]; rows=[]; offs=[]; repstats=[]; sealhash=sha(seal_path); allok=True
 for rep in range(3):
  path=Path(hold_dir)/f'q3_holdout_{rep}.json'
  if not path.exists():return {'holdout_admitted':True,'holdout_verdict':'FAIL','rows':len(rows),'D_star_ms':None,'reason':'missing holdout file'}
  d=json.loads(path.read_text()); ok=d.get('schema')=='replaymark.s2q2-source-holdout-replicate.v1' and d.get('source_only') is True and d.get('shifted_target_executed') is False and d.get('act2_candidate_constructed') is False and d.get('broker')=='mosquitto version 2.1.2' and d.get('holdout_replicate')==rep and d.get('selected_wave_size')==w and d.get('selection_seal_sha256')==sealhash
  v=validate_cell(d.get('cell'),'holdout',rep,None,None,w); ok=ok and v['valid']; allok=allok and ok; rows+=v['rows']; offs+=v['offsets']; prefixes.append(v['prefix']); repstats.append({'replicate':rep,'structurally_valid':ok,'rows':len(v['rows']),'visible_count':sum(bool(r.get('visible_by_verify_deadline')) for r in v['rows']),'p99_ms':pct(v['offsets'],99)})
 complete=len(rows)==576 and len(offs)==576 and all(r.get('completed_by_task_timeout') is True for r in rows); visible=len(rows)==576 and all(r.get('visible_by_verify_deadline') is True for r in rows); fresh=len(prefixes)==3 and len(set(prefixes))==3
 passed=allok and complete and visible and fresh
 median=statistics.median(offs) if offs else None; dstar=math.floor((100.0-median)+0.5) if passed and median is not None else None; admissible=dstar is not None and 1<=dstar<100
 return {'holdout_admitted':True,'holdout_verdict':'PASS' if passed and admissible else 'FAIL','rows':len(rows),'all_rows_structurally_valid':allok,'all_tasks_complete_by_timeout':complete,'all_tasks_visible_by_verify_deadline':visible,'all_namespaces_fresh':fresh,'replicates':repstats,'pooled_median_ms':median,'pooled_p50_ms':pct(offs,50),'pooled_p95_ms':pct(offs,95),'pooled_p99_ms':pct(offs,99),'pooled_max_ms':max(offs) if offs else None,'p99_role':'DESCRIPTIVE_ONLY','D_star_ms':dstar if admissible else None,'D_star_admissible':admissible}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--preflight-only',action='store_true'); ap.add_argument('--screening-dir'); ap.add_argument('--selection-seal'); ap.add_argument('--holdout-dir'); ap.add_argument('--out',required=True); args=ap.parse_args()
 report={'schema':'replaymark.s2q3-boundary-complete-source-verification.v1','preflight':preflight(),'verdict':'PASS'}
 if args.preflight_only:
  Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2)); return
 if not args.screening_dir:raise SystemExit('--screening-dir required')
 s=screening(args.screening_dir); report['screening']=s
 if args.selection_seal:
  sel=make_seal(s); Path(args.selection_seal).write_text(json.dumps(sel,indent=2,sort_keys=True)+'\n'); report['selection_seal_sha256']=sha(args.selection_seal)
 if args.holdout_dir:
  if not args.selection_seal:raise SystemExit('selection seal required for final verification')
  h=holdout(args.holdout_dir,args.selection_seal); report['holdout']=h; report['scientific_verdict']='PASS' if s['screening_verdict']=='PASS' and h['holdout_verdict']=='PASS' else 'FAIL'; report['W_star_screen']=s['W_star_screen']; report['D_star_ms']=h.get('D_star_ms'); report['target_execution_permitted']=report['scientific_verdict']=='PASS'; report['verdict']=report['scientific_verdict']
 Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
