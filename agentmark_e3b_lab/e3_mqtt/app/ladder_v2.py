from __future__ import annotations
import argparse, json, math, os, statistics, time, uuid
from pathlib import Path
from agentmark.certificate import high_confidence_replay_certificate, trace_compatibility
from agentmark.kernel import ReactiveKernel
from experiment import Harness, _sys_delta, percentile
from ladder import spec, offers, source_task, probe, cond, order

PUB = '$SYS/broker/publish/messages/received'
BYTES = '$SYS/broker/publish/bytes/received'

def mean(xs):
    ys=[x for x in xs if x is not None]
    return statistics.mean(ys) if ys else None

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--broker',default=os.getenv('BROKER_HOST','mosquitto'))
    p.add_argument('--port',type=int,default=1883)
    p.add_argument('--tasks',type=int,default=128)
    p.add_argument('--wave-size',type=int,default=32)
    p.add_argument('--wave-period-ms',type=int,default=300)
    p.add_argument('--verify-floor-ms',type=float,default=100)
    p.add_argument('--source-guard-ms',type=float,default=20)
    p.add_argument('--changed-delay-floor-ms',type=float,default=150)
    p.add_argument('--target-margin-ms',type=float,default=50)
    p.add_argument('--post-completion-gap-ms',type=float,default=20)
    p.add_argument('--task-timeout-ms',type=int,default=1200)
    p.add_argument('--trials',type=int,default=12)
    p.add_argument('--out',default='/results/e3b_r0_r1_r2_certificate.json')
    a=p.parse_args()
    if a.tasks % a.wave_size: raise ValueError('tasks must be divisible by wave size')
    h=Harness(a.broker,a.port)
    try:
        version=h.broker_version()
        # Source world is observed first. The target world is not inspected until
        # the controller decision boundary has been frozen.
        h.set_state_delay(0)
        traces=offers(a.tasks,a.wave_size,a.wave_period_ms,lambda i,o:source_task(h,i,f'source-{uuid.uuid4().hex[:6]}',o,a.post_completion_gap_ms,a.task_timeout_ms))
        first=[float(x['first_completion_offset_ms']) for x in traces]
        source_p99=percentile(first,99); source_max=max(first)
        verify_ms=max(float(a.verify_floor_ms), float(math.ceil(source_max+a.source_guard_ms)))
        target_delay_ms=max(float(a.changed_delay_floor_ms), verify_ms+a.target_margin_ms)
        if target_delay_ms>=a.task_timeout_ms: raise RuntimeError('calibrated target delay collides with task timeout')
        source_trace_valid=all(x<=verify_ms for x in first)

        # Controller-neutral prefix probes estimate feedback laws; no R2 recovery
        # traffic is allowed to contaminate the certificate inputs.
        h.set_state_delay(0)
        source_counts=probe(h,a.tasks,a.wave_size,a.wave_period_ms,f'ps-{uuid.uuid4().hex[:6]}',verify_ms,a.task_timeout_ms)
        h.set_state_delay(target_delay_ms)
        target_counts=probe(h,a.tasks,a.wave_size,a.wave_period_ms,f'pt-{uuid.uuid4().hex[:6]}',verify_ms,a.task_timeout_ms)

        k=ReactiveKernel(spec())
        cert=high_confidence_replay_certificate(k,'after_act1',source_counts,target_counts,projection='operation')
        cls='CERTIFIED_UNSAFE' if cert['true_live_workload_shift_tv_lower']>.05 else ('CERTIFIED_SAFE' if cert['certified_safe_at_epsilon'] else 'UNRESOLVED')
        compat=trace_compatibility(k,[{'state':'after_act1','source_feedback':'confirmed_by_deadline','target_feedback':'not_visible_by_deadline','operation':'ACT2'}])

        trials=[]
        for t in range(a.trials):
            row={'trial':t,'order':order(t),'modes':{}}
            for mode in row['order']:
                h.set_state_delay(target_delay_ms)
                before=h.fresh_sys_snapshot()
                r=cond(h,mode,traces,a.wave_size,a.wave_period_ms,f't{t}-{mode}-{uuid.uuid4().hex[:5]}',verify_ms,a.post_completion_gap_ms,a.task_timeout_ms)
                time.sleep(target_delay_ms/1000.0+.05)
                after=h.fresh_sys_snapshot()
                r['sys']=_sys_delta(before,after)
                observed=float(r['sys'].get(PUB,float('nan')))
                expected=float(4*r['tasks']+2*r['verify_count'])
                r['publish_conservation']={'expected':expected,'observed':observed,'error':observed-expected,'exact':math.isfinite(observed) and observed==expected}
                row['modes'][mode]=r
            trials.append(row)
    finally:
        h.close()

    derived=[]
    for row in trials:
        r0=row['modes']['R0_rigid']; r1=row['modes']['R1_timing']; r2=row['modes']['R2_semantic']
        sv=lambda r,k: float(r['sys'].get(k,0))
        derived.append({
          'trial':row['trial'],'order':row['order'],
          'r0_violation':r0['support_violation_fraction'],'r1_violation':r1['support_violation_fraction'],'r2_violation':r2['support_violation_fraction'],
          'r2_verify_fraction':r2['verify_count']/r2['tasks'],
          'r1_timing_shift_ms':r1['act2_mean_ms']-r0['act2_mean_ms'],
          'r2_ops_over_r1':r2['semantic_operations']/r1['semantic_operations'],
          'r2_publish_over_r1':sv(r2,PUB)/sv(r1,PUB) if sv(r1,PUB) else None,
          'r2_bytes_over_r1':sv(r2,BYTES)/sv(r1,BYTES) if sv(r1,BYTES) else None,
          'r0_p99':r0['p99_ms'],'r1_p99':r1['p99_ms'],'r2_p99':r2['p99_ms']})
    agg={k:mean([d[k] for d in derived]) for k in derived[0] if k not in ('trial','order')}
    conservation=[{'trial':row['trial'],'mode':m,**row['modes'][m]['publish_conservation']} for row in trials for m in ('R0_rigid','R1_timing','R2_semantic')]
    checks={
      'source_recorded_trace_controller_valid':source_trace_valid,
      'target_feedback_shift_observed':target_counts['not_visible_by_deadline']>source_counts['not_visible_by_deadline'],
      'certificate_not_safe':cls!='CERTIFIED_SAFE',
      'recorded_act2_is_target_support_failure':compat['support_failures']==1,
      'r0_semantic_support_breaks':agg['r0_violation']>0,
      'r1_timing_only_still_semantically_breaks':agg['r1_violation']>0,
      'r2_preserves_policy_support':agg['r2_violation']==0,
      'r1_actually_changes_timing':abs(agg['r1_timing_shift_ms'])>1,
      'broker_publish_conservation_exact':all(x['exact'] for x in conservation),
      'broker_native_counter_available':all(PUB in row['modes'][m]['sys'] for row in trials for m in row['modes'])}
    report={
      'schema':'agentmark.e3b.r0_r1_r2_certificate.v2','gate':'E3b Mosquitto decisive ladder',
      'broker_version_sys':version,
      'parameters':{**vars(a),'calibrated_verify_ms':verify_ms,'calibrated_target_delay_ms':target_delay_ms},
      'calibration':{'source_first_completion_p99_ms':source_p99,'source_first_completion_max_ms':source_max,'source_guard_ms':a.source_guard_ms,'source_trace_controller_valid':source_trace_valid},
      'prefix_probe':{'source_counts':source_counts,'target_counts':target_counts},
      'replay_safety_certificate':{**cert,'classification':cls},
      'recorded_act2_under_changed_feedback':compat,
      'replay_taxonomy':{'R0_rigid':'source semantic sequence and source issue offsets frozen','R1_timing':'semantic sequence frozen; timing follows target completion','R2_semantic':'timing plus policy-permitted VERIFY insertion'},
      'aggregate':agg,'broker_publish_conservation':conservation,'derived_trials':derived,'trials':trials,
      'promotion_checks':checks,'promotion_pass':all(checks.values())}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'promotion_pass':report['promotion_pass'],'broker_version_sys':version,'calibrated_verify_ms':verify_ms,'calibrated_target_delay_ms':target_delay_ms,'source_counts':source_counts,'target_counts':target_counts,'certificate':cls,'certificate_tv_lower':cert['true_live_workload_shift_tv_lower'],'aggregate':agg,'publish_conservation_exact':checks['broker_publish_conservation_exact']},indent=2,sort_keys=True))
    if not report['promotion_pass']: raise SystemExit(2)
if __name__=='__main__': main()
