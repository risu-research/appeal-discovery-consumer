#!/usr/bin/env python3
from collections import defaultdict, deque
from itertools import combinations, product
import json

def part(xs, sig):
    d=defaultdict(list)
    for x in xs:d[sig(x)].append(x)
    return tuple(tuple(v) for v in d.values())
def rel(xs, leq, qeq):
    d=defaultdict(int)
    for a,b in combinations(xs,2):d[(leq(a,b),qeq(a,b))]+=1
    return {"FF":d[(False,False)],"FT":d[(False,True)],"TF":d[(True,False)],"TT":d[(True,True)]}

# E3b exact operation-level model from ladder.py blob fcc1768544714f1b11a497a856f8e18d4d2f07dd.
ES=("after_act1","verified","done"); EY=("confirmed_by_deadline","not_visible_by_deadline")
def eo(d):
    s,y=d
    if s=="after_act1":return ("ACT2","done") if y==EY[0] else ("VERIFY","verified")
    if s=="verified":return "ACT2","done"
    return "DONE","done"
def esig(d,h):
    o,n=eo(d)
    return (o,) if h==0 else (o,tuple((y,esig((n,y),h-1)) for y in EY))
def ereport():
    xs=tuple(product(ES,EY)); ps=[part(xs,lambda x,h=h:esig(x,h)) for h in range(4)]
    assert list(map(len,ps))==[3,3,3,3]
    local=lambda a,b:a[0]==b[0] and eo(a)[0]==eo(b)[0]
    rr=rel(xs,local,lambda a,b:esig(a,3)==esig(b,3)); assert rr=={"FF":11,"FT":2,"TF":0,"TT":2}
    return {"raw":6,"local_classes":4,"q_counts":[3,3,3,3],"stable_h":0,"stable_q":3,"pair_relation":rr}

# Pinned Better Thermostat 57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f.
# Frozen N2/N2b inputs: enable on, writeback false, boost/eco/activity absent.
P=("away","home","comfort","sleep"); ALL=P+("boost","eco","activity")
EV=("presence_toggle","motion_toggle","night_toggle","tick")
def tgt(s):
    p,m,n=s[:3]
    if n:return "sleep"
    if not p:return "away"
    if m:return "comfort"
    return "home"
def out(s):return "NO_ACTION" if s[3]==tgt(s) else "SET_"+tgt(s).upper()
def step(s,e):
    p,m,n,_=s; c=tgt(s)
    if e==EV[0]:p=not p
    elif e==EV[1]:m=not m
    elif e==EV[2]:n=not n
    return p,m,n,c
def tsig(s,h):return (out(s),) if h==0 else (out(s),tuple((e,tsig(step(s,e),h-1)) for e in EV))
def wordout(s,w):
    r=[]
    for e in w:s=step(s,e);r.append(out(s))
    return tuple(r)
def shortest(a,b):
    if out(a)!=out(b):return (), (out(a),),(out(b),)
    q=deque([(a,b,())]);seen={(a,b)}
    while q:
        a0,b0,w=q.popleft()
        for e in EV:
            a1,b1=step(a0,e),step(b0,e);w1=w+(e,)
            if out(a1)!=out(b1):return w1,wordout(a,w1),wordout(b,w1)
            if (a1,b1) not in seen:seen.add((a1,b1));q.append((a1,b1,w1))
def treport():
    xs=tuple((p,m,n,c) for p,m,n in product((False,True),repeat=3) for c in P)
    allx=tuple((p,m,n,c) for p,m,n in product((False,True),repeat=3) for c in ALL)
    ps=[part(xs,lambda x,h=h:tsig(x,h)) for h in range(5)]; assert list(map(len,ps))==[5,14,16,16,16]
    key=lambda s:(s[0],s[1],s[2],s[3]==tgt(s))
    for a,b in combinations(allx,2):assert (tsig(a,4)==tsig(b,4))==(key(a)==key(b))
    local=lambda a,b:a[3]==b[3] and out(a)==out(b)
    rr=rel(xs,local,lambda a,b:tsig(a,4)==tsig(b,4));assert rr=={"FF":444,"FT":24,"TF":28,"TT":0}
    h0=stable=0;dh=defaultdict(int);ldh=defaultdict(int)
    for a,b in combinations(xs,2):
        same=out(a)==out(b)
        if same:
            h0+=1
            if tsig(a,4)==tsig(b,4):stable+=1
            else:dh[len(shortest(a,b)[0])]+=1
        if local(a,b) and tsig(a,4)!=tsig(b,4):ldh[len(shortest(a,b)[0])]+=1
    assert (h0,stable,dict(dh),dict(ldh))==(115,24,{1:81,2:10},{1:24,2:4})
    n2a=(False,False,False,"sleep");n2b=(False,True,False,"sleep");w1=shortest(n2a,n2b)
    assert w1==((EV[0],),("SET_HOME",),("SET_COMFORT",))
    d2a=(False,False,True,"sleep");d2b=(False,True,True,"sleep");w2=shortest(d2a,d2b)
    assert w2==((EV[0],EV[2]),("NO_ACTION","SET_HOME"),("NO_ACTION","SET_COMFORT"))
    return {"raw":32,"all_declared_preset_raw":56,"local_classes":16,"q_counts":[5,14,16,16,16],"stable_h":2,"stable_q":16,"stable_key":"presence,motion,night,at_target","pair_relation":rr,"h0_equal_pairs":115,"h0_stable_pairs":24,"h0_split_depth":{"1":81,"2":10},"local_split_depth":{"1":24,"2":4},"n2b_witness":{"suffix":w1[0],"a":w1[1],"b":w1[2]},"depth2_witness":{"suffix":w2[0],"a":w2[1],"b":w2[2]}}

if __name__=="__main__":
    print(json.dumps({"schema":"replaymark.claim_predictive_state.full_gate.compact.v1","e3b":ereport(),"better_thermostat":treport()},indent=2,sort_keys=True))
