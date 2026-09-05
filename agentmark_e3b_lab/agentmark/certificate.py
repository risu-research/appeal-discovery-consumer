from __future__ import annotations
import math
from typing import Any, Iterable, Mapping
from .kernel import ReactiveKernel
from .minimize import quotient

def _normalize(dist):
    out={str(k):float(v) for k,v in dist.items() if float(v)>0}; t=sum(out.values())
    if t<=0: raise ValueError('distribution must have positive mass')
    return {k:v/t for k,v in out.items()}

def _tv(a,b): return 0.5*sum(abs(float(a.get(k,0))-float(b.get(k,0))) for k in set(a)|set(b))
def _push(kernel,state,mu,projection='operation'):
    q=quotient(kernel); out={}
    for y,m in _normalize(mu).items():
        for e,p in kernel.distribution(state,y,state_blocks=q.state_to_block,projection=projection).items(): out[e]=out.get(e,0)+m*float(p)
    return out

def eta(kernel,state,projection='operation'):
    ys=[y for y in kernel.feedback_alphabet if kernel.has_feedback(state,y)]; best=0.0
    q=quotient(kernel)
    for i,a in enumerate(ys):
        da={k:float(v) for k,v in kernel.distribution(state,a,state_blocks=q.state_to_block,projection=projection).items()}
        for b in ys[i+1:]:
            db={k:float(v) for k,v in kernel.distribution(state,b,state_blocks=q.state_to_block,projection=projection).items()}; best=max(best,_tv(da,db))
    return best

def weissman_tv_radius(n,k,delta):
    if k==1:return 0.0
    logp=k*math.log(2.0)+math.log1p(-2.0**(1-k))
    return min(1.0,math.sqrt(max(0.0,(logp-math.log(delta))/(2.0*n))))
def high_confidence_replay_certificate(kernel,state,source_counts,target_counts,*,delta=0.05,epsilon=0.05,projection='operation'):
    alphabet=tuple(y for y in kernel.feedback_alphabet if kernel.has_feedback(state,y))
    ns=sum(source_counts.values()); nt=sum(target_counts.values())
    src={y:source_counts.get(y,0)/ns for y in alphabet}; tgt={y:target_counts.get(y,0)/nt for y in alphabet}
    rs=weissman_tv_radius(ns,len(alphabet),delta/2); rt=weissman_tv_radius(nt,len(alphabet),delta/2)
    ws=_push(kernel,state,src,projection); wt=_push(kernel,state,tgt,projection); empirical=_tv(ws,wt); e=eta(kernel,state,projection)
    uncertainty=min(1.0,e*(rs+rt)); upper=min(1.0,empirical+uncertainty); lower=max(0.0,empirical-uncertainty)
    return {'schema':'agentmark.replay_certificate.high_confidence.v1','confidence':1-delta,'epsilon':epsilon,'source_n':ns,'target_n':nt,'source_empirical_feedback':src,'target_empirical_feedback':tgt,'source_feedback_tv_radius':rs,'target_feedback_tv_radius':rt,'policy_feedback_sensitivity_eta':e,'empirical_live_workload_shift_tv':empirical,'true_live_workload_shift_tv_lower':lower,'true_live_workload_shift_tv_upper':upper,'certified_safe_at_epsilon':upper<=epsilon}
def trace_compatibility(kernel,rows:Iterable[Mapping[str,Any]]):
    details=[]; failures=0; inconsist=0; logratio=0.0
    for i,row in enumerate(rows):
        kw={'operation':str(row['operation'])}
        ps=float(kernel.event_probability(str(row['state']),str(row['source_feedback']),**kw)); pt=float(kernel.event_probability(str(row['state']),str(row['target_feedback']),**kw))
        sb=ps<=0; sf=ps>0 and pt<=0
        if sb: inconsist+=1; step=None
        elif sf: failures+=1; step=-math.inf; logratio=-math.inf
        else: step=math.log(pt/ps); logratio=logratio+step if math.isfinite(logratio) else logratio
        details.append({'index':i,'p_source':ps,'p_target':pt,'source_inconsistent':sb,'support_failure':sf,'log_target_over_source':step})
    return {'schema':'agentmark.trace_compatibility.v2','rows':details,'support_failures':failures,'source_inconsistencies':inconsist,'target_supports_entire_recorded_controller_trace':failures==0 and inconsist==0,'conditional_controller_log_likelihood_ratio':logratio,'conditional_controller_likelihood_ratio':0.0 if logratio==-math.inf else math.exp(logratio)}
