from __future__ import annotations
import argparse,json,os,statistics,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from agentmark.certificate import high_confidence_replay_certificate,trace_compatibility
from agentmark.kernel import ReactiveKernel
from experiment import Harness,_sys_delta,percentile

def spec():
 return {'initial_state':'after_act1','feedback_alphabet':['confirmed_by_deadline','not_visible_by_deadline'],'states':{'after_act1':{'confirmed_by_deadline':[{'p':1,'operation':'ACT2','target_class':'stage2','next_state':'done'}],'not_visible_by_deadline':[{'p':1,'operation':'VERIFY','target_class':'stage1','next_state':'verified'}]},'verified':{'confirmed_by_deadline':[{'p':1,'operation':'ACT2','target_class':'stage2','next_state':'done'}],'not_visible_by_deadline':[{'p':1,'operation':'ACT2','target_class':'stage2','next_state':'done'}]},'done':{'confirmed_by_deadline':[{'p':1,'operation':'DONE','next_state':'done'}],'not_visible_by_deadline':[{'p':1,'operation':'DONE','next_state':'done'}]}}}
def sleep_until(ns):
 while True:
  r=ns-time.monotonic_ns()
  if r<=0:return
  time.sleep(r/1e9)
def pub(h,topic,body):
 ts=time.monotonic_ns(); i=h.client.publish(topic,json.dumps(body,sort_keys=True),qos=1); i.wait_for_publish(timeout=5); return ts
def offers(n,wave,period,fn):
 base=time.monotonic_ns()+100_000_000; rows=[]
 with ThreadPoolExecutor(max_workers=n) as p:
  fs=[p.submit(fn,i,base+(i//wave)*int(period*1e6)) for i in range(n)]
  for f in as_completed(fs):rows.append(f.result())
 return sorted(rows,key=lambda x:x['task_id'])
def source_task(h,i,prefix,offer,gap,timeout):
 sleep_until(offer); t0=time.monotonic_ns(); a=f'{prefix}-{i}-a';b=f'{prefix}-{i}-b'; a1=pub(h,f'agentmark/{a}/command',{'on':True}); d=t0+int(timeout*1e6); e1=h.wait_state_on_until(a,d,after_ns=a1)
 if e1 is None:raise TimeoutError('source1')
 sleep_until(e1['recv_mono_ns']+int(gap*1e6)); a2=pub(h,f'agentmark/{b}/command',{'on':True}); e2=h.wait_state_on_until(b,d,after_ns=a2)
 if e2 is None:raise TimeoutError('source2')
 return {'task_id':i,'act2_offset_ms':(a2-t0)/1e6,'first_completion_offset_ms':(e1['recv_mono_ns']-t0)/1e6}
def probe_task(h,i,prefix,offer,verify,timeout):
 sleep_until(offer);t0=time.monotonic_ns();a=f'{prefix}-{i}-a';a1=pub(h,f'agentmark/{a}/command',{'on':True});vd=t0+int(verify*1e6);e=h.wait_state_on_until(a,vd,after_ns=a1);sym='confirmed_by_deadline' if e else 'not_visible_by_deadline'
 if e is None:h.wait_state_on_until(a,t0+int(timeout*1e6),after_ns=a1)
 return {'task_id':i,'feedback':sym}
def probe(h,n,wave,period,prefix,verify,timeout):
 rows=offers(n,wave,period,lambda i,o:probe_task(h,i,prefix,o,verify,timeout));c={'confirmed_by_deadline':0,'not_visible_by_deadline':0}
 for r in rows:c[r['feedback']]+=1
 return c
def target_task(h,mode,i,prefix,offer,tr,verify,gap,timeout):
 sleep_until(offer);t0=time.monotonic_ns();a=f'{prefix}-{i}-a';b=f'{prefix}-{i}-b';ops=[];a1=pub(h,f'agentmark/{a}/command',{'on':True});ops.append('ACT1');vd=t0+int(verify*1e6);td=t0+int(timeout*1e6);first=None
 if mode=='R0_rigid':
  box=[None]
  th=threading.Thread(target=lambda:box.__setitem__(0,h.wait_state_on_until(a,vd,after_ns=a1)),daemon=True);th.start();sleep_until(t0+int(tr['act2_offset_ms']*1e6));a2=pub(h,f'agentmark/{b}/command',{'on':True});ops.append('ACT2');th.join(timeout=.2);first=box[0];branch=first is None;viol=branch
 elif mode=='R1_timing':
  first=h.wait_state_on_until(a,td,after_ns=a1)
  if first is None:return {'task_id':i,'success':False,'branch':True,'violation':True,'verify':0,'ops':ops,'lat':(time.monotonic_ns()-t0)/1e6,'act2':None}
  branch=first['recv_mono_ns']>vd;viol=branch;sleep_until(first['recv_mono_ns']+int(gap*1e6));a2=pub(h,f'agentmark/{b}/command',{'on':True});ops.append('ACT2')
 else:
  first=h.wait_state_on_until(a,vd,after_ns=a1);branch=first is None;viol=False
  if first is None:
   q=pub(h,f'agentmark/{a}/query',{});ops.append('VERIFY');first=h.wait_state_on_until(a,td,after_ns=q)
   if first is None:return {'task_id':i,'success':False,'branch':True,'violation':False,'verify':1,'ops':ops,'lat':(time.monotonic_ns()-t0)/1e6,'act2':None}
  sleep_until(first['recv_mono_ns']+int(gap*1e6));a2=pub(h,f'agentmark/{b}/command',{'on':True});ops.append('ACT2')
 ea=h.wait_state_on_until(a,td,after_ns=a1);eb=h.wait_state_on_until(b,td,after_ns=a2);success=ea is not None and eb is not None
 return {'task_id':i,'success':success,'branch':branch,'violation':viol,'verify':ops.count('VERIFY'),'ops':ops,'lat':(max([x['recv_mono_ns'] for x in (ea,eb) if x]or[time.monotonic_ns()])-t0)/1e6,'act2':(a2-t0)/1e6}
def cond(h,mode,traces,wave,period,prefix,verify,gap,timeout):
 by={x['task_id']:x for x in traces};rows=offers(len(traces),wave,period,lambda i,o:target_task(h,mode,i,prefix,o,by[i],verify,gap,timeout));lat=[r['lat'] for r in rows if r['success']];a2=[r['act2'] for r in rows if r['act2'] is not None];n=len(rows)
 return {'tasks':n,'success_rate':sum(r['success'] for r in rows)/n,'support_violation_fraction':sum(r['violation'] for r in rows)/n,'branch_required_fraction':sum(r['branch'] for r in rows)/n,'verify_count':sum(r['verify'] for r in rows),'semantic_operations':sum(len(r['ops']) for r in rows),'p99_ms':percentile(lat,99),'act2_mean_ms':statistics.mean(a2) if a2 else None}
def order(t):
 ps=[['R0_rigid','R1_timing','R2_semantic'],['R1_timing','R2_semantic','R0_rigid'],['R2_semantic','R0_rigid','R1_timing'],['R0_rigid','R2_semantic','R1_timing'],['R2_semantic','R1_timing','R0_rigid'],['R1_timing','R0_rigid','R2_semantic']];return ps[t%6]
def main():
 p=argparse.ArgumentParser();p.add_argument('--broker',default=os.getenv('BROKER_HOST','mosquitto'));p.add_argument('--port',type=int,default=1883);p.add_argument('--tasks',type=int,default=128);p.add_argument('--wave-size',type=int,default=32);p.add_argument('--wave-period-ms',type=int,default=300);p.add_argument('--verify-ms',type=int,default=100);p.add_argument('--changed-delay-ms',type=int,default=150);p.add_argument('--post-completion-gap-ms',type=float,default=20);p.add_argument('--task-timeout-ms',type=int,default=1200);p.add_argument('--trials',type=int,default=12);p.add_argument('--out',default='/results/e3b_r0_r1_r2_certificate.json');a=p.parse_args();h=Harness(a.broker,a.port)
 try:
  ver=h.broker_version();h.set_state_delay(0);tr=offers(a.tasks,a.wave_size,a.wave_period_ms,lambda i,o:source_task(h,i,'source',o,a.post_completion_gap_ms,a.task_timeout_ms));sp99=percentile([x['first_completion_offset_ms'] for x in tr],99)
  if sp99>=a.verify_ms:raise RuntimeError(f'source not clean p99={sp99}')
  h.set_state_delay(0);sc=probe(h,a.tasks,a.wave_size,a.wave_period_ms,'ps',a.verify_ms,a.task_timeout_ms);h.set_state_delay(a.changed_delay_ms);tc=probe(h,a.tasks,a.wave_size,a.wave_period_ms,'pt',a.verify_ms,a.task_timeout_ms)
  k=ReactiveKernel(spec());cert=high_confidence_replay_certificate(k,'after_act1',sc,tc,projection='operation');cls='CERTIFIED_UNSAFE' if cert['true_live_workload_shift_tv_lower']>.05 else ('CERTIFIED_SAFE' if cert['certified_safe_at_epsilon'] else 'UNRESOLVED');compat=trace_compatibility(k,[{'state':'after_act1','source_feedback':'confirmed_by_deadline','target_feedback':'not_visible_by_deadline','operation':'ACT2'}]);trials=[]
  for t in range(a.trials):
   row={'trial':t,'order':order(t),'modes':{}}
   for m in row['order']:
    h.set_state_delay(a.changed_delay_ms);before=h.fresh_sys_snapshot();r=cond(h,m,tr,a.wave_size,a.wave_period_ms,f't{t}-{m}',a.verify_ms,a.post_completion_gap_ms,a.task_timeout_ms);time.sleep(a.changed_delay_ms/1000+.05);after=h.fresh_sys_snapshot();r['sys']=_sys_delta(before,after);row['modes'][m]=r
   trials.append(row)
 finally:h.close()
 pk='$SYS/broker/publish/messages/received';bk='$SYS/broker/publish/bytes/received';ds=[]
 for x in trials:
  r0=x['modes']['R0_rigid'];r1=x['modes']['R1_timing'];r2=x['modes']['R2_semantic'];sv=lambda r,k:float(r['sys'].get(k,0));ds.append({'r0v':r0['support_violation_fraction'],'r1v':r1['support_violation_fraction'],'r2v':r2['support_violation_fraction'],'verify':r2['verify_count']/r2['tasks'],'shift':r1['act2_mean_ms']-r0['act2_mean_ms'],'ops':r2['semantic_operations']/r1['semantic_operations'],'pub':sv(r2,pk)/sv(r1,pk) if sv(r1,pk) else None,'bytes':sv(r2,bk)/sv(r1,bk) if sv(r1,bk) else None,'r0p99':r0['p99_ms'],'r1p99':r1['p99_ms'],'r2p99':r2['p99_ms']})
 mean=lambda k:statistics.mean([d[k] for d in ds if d[k] is not None]);agg={'r0_support_violation_fraction_mean':mean('r0v'),'r1_support_violation_fraction_mean':mean('r1v'),'r2_support_violation_fraction_mean':mean('r2v'),'r2_verify_fraction_mean':mean('verify'),'r1_act2_timing_shift_ms_vs_r0_mean':mean('shift'),'r2_semantic_ops_over_r1_mean':mean('ops'),'r2_broker_publish_over_r1_mean':mean('pub'),'r2_broker_bytes_over_r1_mean':mean('bytes'),'r0_p99_ms_mean':mean('r0p99'),'r1_p99_ms_mean':mean('r1p99'),'r2_p99_ms_mean':mean('r2p99')};checks={'source_clean':sc['not_visible_by_deadline']==0,'target_shift':tc['not_visible_by_deadline']>0,'certificate_not_safe':cls!='CERTIFIED_SAFE','r0_breaks':agg['r0_support_violation_fraction_mean']>0,'r1_breaks':agg['r1_support_violation_fraction_mean']>0,'r2_support':agg['r2_support_violation_fraction_mean']==0,'r1_timing_changes':abs(agg['r1_act2_timing_shift_ms_vs_r0_mean'])>1,'broker_counter':all(pk in x['modes'][m]['sys'] for x in trials for m in x['modes'])};report={'schema':'agentmark.e3b.r0_r1_r2_certificate.v1','gate':'E3b Mosquitto R0/R1/R2 + Replay Safety Certificate','broker_version_sys':ver,'source_trace_summary':{'first_completion_p99_ms':sp99},'prefix_probe':{'source_counts':sc,'target_counts':tc},'replay_safety_certificate':{**cert,'classification':cls},'recorded_act2_under_timeout_compatibility':compat,'trials':trials,'aggregate':agg,'promotion_checks':checks,'promotion_pass':all(checks.values())};Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'promotion_pass':report['promotion_pass'],'certificate':cls,**agg},indent=2))
if __name__=='__main__':main()
