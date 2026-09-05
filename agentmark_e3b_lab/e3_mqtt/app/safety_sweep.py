from __future__ import annotations
import argparse,json,math,os,statistics,time,uuid
from pathlib import Path
from agentmark.certificate import high_confidence_replay_certificate
from agentmark.kernel import ReactiveKernel
from experiment import Harness,_sys_delta
from ladder import cond,offers,probe,source_task,spec
PUB='$SYS/broker/publish/messages/received'
def cls(c,e):
 if c['true_live_workload_shift_tv_lower']>e:return 'CERTIFIED_UNSAFE'
 if c['certified_safe_at_epsilon']:return 'CERTIFIED_SAFE'
 return 'UNRESOLVED'
def insensitive_spec():
 row=[{'p':1,'operation':'ACT2','target_class':'stage2','next_state':'done'}];done=[{'p':1,'operation':'DONE','next_state':'done'}]
 return {'initial_state':'after_act1','feedback_alphabet':['confirmed_by_deadline','not_visible_by_deadline'],'states':{'after_act1':{'confirmed_by_deadline':row,'not_visible_by_deadline':row},'done':{'confirmed_by_deadline':done,'not_visible_by_deadline':done}}}
def mean(xs):
 xs=[float(x) for x in xs if x is not None];return statistics.mean(xs) if xs else None
def main():
 p=argparse.ArgumentParser();p.add_argument('--broker',default=os.getenv('BROKER_HOST','mosquitto'));p.add_argument('--port',type=int,default=1883);p.add_argument('--tasks',type=int,default=128);p.add_argument('--wave-size',type=int,default=32);p.add_argument('--wave-period-ms',type=int,default=300);p.add_argument('--verify-floor-ms',type=float,default=100);p.add_argument('--source-guard-ms',type=float,default=20);p.add_argument('--offsets-ms',default='-40,-20,-5,0,10,25,50');p.add_argument('--post-completion-gap-ms',type=float,default=20);p.add_argument('--task-timeout-ms',type=int,default=1200);p.add_argument('--paired-trials',type=int,default=3);p.add_argument('--epsilon',type=float,default=.05);p.add_argument('--out',default='/results/e3b_replay_safety_sweep.json');a=p.parse_args();h=Harness(a.broker,a.port)
 try:
  ver=h.broker_version();h.set_state_delay(0);tr=offers(a.tasks,a.wave_size,a.wave_period_ms,lambda i,o:source_task(h,i,f'ss-{uuid.uuid4().hex[:5]}',o,a.post_completion_gap_ms,a.task_timeout_ms));sf=[float(x['first_completion_offset_ms']) for x in tr];verify=max(a.verify_floor_ms,float(math.ceil(max(sf)+a.source_guard_ms)));valid=all(x<=verify for x in sf);h.set_state_delay(0);sc=probe(h,a.tasks,a.wave_size,a.wave_period_ms,f'sps-{uuid.uuid4().hex[:5]}',verify,a.task_timeout_ms);k=ReactiveKernel(spec());ki=ReactiveKernel(insensitive_spec());points=[]
  for j,off in enumerate(int(x) for x in a.offsets_ms.split(',')):
   delay=max(0,int(round(verify+off)));h.set_state_delay(delay);tc=probe(h,a.tasks,a.wave_size,a.wave_period_ms,f'spt{j}-{uuid.uuid4().hex[:5]}',verify,a.task_timeout_ms);cert=high_confidence_replay_certificate(k,'after_act1',sc,tc,epsilon=a.epsilon,projection='operation');safe=high_confidence_replay_certificate(ki,'after_act1',sc,tc,epsilon=a.epsilon,projection='operation');paired=[]
   for t in range(a.paired_trials):
    modes=['R1_timing','R2_semantic'] if (t+j)%2==0 else ['R2_semantic','R1_timing'];rr={'trial':t,'order':modes,'modes':{}}
    for m in modes:
     h.set_state_delay(delay);before=h.fresh_sys_snapshot();r=cond(h,m,tr,a.wave_size,a.wave_period_ms,f'sw{j}-{t}-{m}-{uuid.uuid4().hex[:4]}',verify,a.post_completion_gap_ms,a.task_timeout_ms);time.sleep(delay/1000+.05);after=h.fresh_sys_snapshot();r['sys']=_sys_delta(before,after);obs=float(r['sys'].get(PUB,float('nan')));exp=float(4*r['tasks']+2*r['verify_count']);r['publish_conservation_exact']=math.isfinite(obs) and obs==exp;rr['modes'][m]=r
    paired.append(rr)
   sm=sc['not_visible_by_deadline']/a.tasks;tm=tc['not_visible_by_deadline']/a.tasks;r1v=mean([x['modes']['R1_timing']['support_violation_fraction'] for x in paired]);r2v=mean([x['modes']['R2_semantic']['verify_count']/a.tasks for x in paired]);pr=mean([float(x['modes']['R2_semantic']['sys'][PUB])/float(x['modes']['R1_timing']['sys'][PUB]) for x in paired]);points.append({'offset_ms':off,'delay_ms':delay,'source_miss_rate':sm,'target_miss_rate':tm,'empirical_feedback_tv':abs(tm-sm),'certificate':{**cert,'classification':cls(cert,a.epsilon)},'feedback_insensitive_control':{**safe,'classification':cls(safe,a.epsilon)},'r1_support_violation_fraction_mean':r1v,'r2_verify_fraction_mean':r2v,'r2_broker_publish_over_r1_mean':pr,'all_publish_conservation_exact':all(x['modes'][m]['publish_conservation_exact'] for x in paired for m in ('R1_timing','R2_semantic')),'paired_trials':paired})
 finally:h.close()
 report={'schema':'agentmark.e3b.replay_safety_sweep.v1','broker_version_sys':ver,'parameters':{**vars(a),'calibrated_verify_ms':verify},'source':{'controller_valid':valid,'feedback_counts':sc,'first_completion_max_ms':max(sf)},'points':points,'checks':{'source_controller_valid':valid,'all_broker_publish_conservation_exact':all(x['all_publish_conservation_exact'] for x in points),'insensitive_control_always_certified_safe':all(x['feedback_insensitive_control']['classification']=='CERTIFIED_SAFE' for x in points),'boundary_contains_changed_feedback':any(x['target_miss_rate']>x['source_miss_rate'] for x in points)}};Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'broker':ver,'verify_ms':verify,'points':[{'offset':x['offset_ms'],'miss':x['target_miss_rate'],'class':x['certificate']['classification'],'r1v':x['r1_support_violation_fraction_mean'],'r2v':x['r2_verify_fraction_mean'],'pub_ratio':x['r2_broker_publish_over_r1_mean']} for x in points],'checks':report['checks']},indent=2))
if __name__=='__main__':main()
