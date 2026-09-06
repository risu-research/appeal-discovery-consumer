#!/usr/bin/env python3
from collections import defaultdict
from itertools import product

# Independent validator: iterative partition refinement only; does not reuse recursive signatures.

ES=("after_act1","verified","done"); EY=("confirmed_by_deadline","not_visible_by_deadline"); ED=tuple(product(ES,EY))
def eo(d):
 s,y=d
 if s=="after_act1":return "ACT2" if y==EY[0] else "VERIFY"
 if s=="verified":return "ACT2"
 return "DONE"
def enext(d,y2):
 s,y=d
 if s=="after_act1":ns="done" if y==EY[0] else "verified"
 elif s=="verified":ns="done"
 else:ns="done"
 return ns,y2

P=("away","home","comfort","sleep"); TD=tuple((p,m,n,c) for p,m,n in product((False,True),repeat=3) for c in P); TI=("P","M","N","T")
def tgt(s):
 p,m,n,_=s
 if n:return "sleep"
 if not p:return "away"
 if m:return "comfort"
 return "home"
def to(s):return "NO_ACTION" if s[3]==tgt(s) else "SET_"+tgt(s).upper()
def tnext(s,e):
 p,m,n,_=s;c=tgt(s)
 if e=="P":p=not p
 elif e=="M":m=not m
 elif e=="N":n=not n
 return p,m,n,c

def refine(items,inputs,outfn,nextfn):
 ids={};block={}
 for x in items:
  k=outfn(x);ids.setdefault(k,len(ids));block[x]=ids[k]
 counts=[len(set(block.values()))]
 while True:
  ids={};new={}
  for x in items:
   k=(outfn(x),tuple(block[nextfn(x,i)] for i in inputs));ids.setdefault(k,len(ids));new[x]=ids[k]
  counts.append(len(set(new.values())))
  same=all((block[a]==block[b])==(new[a]==new[b]) for a in items for b in items)
  block=new
  if same:return counts,block

ec,eb=refine(ED,EY,eo,enext);tc,tb=refine(TD,TI,to,tnext)
assert ec[:2]==[3,3] and len(set(eb.values()))==3,ec
assert tc[:4]==[5,14,16,16] and len(set(tb.values()))==16,tc
for a in TD:
 for b in TD:
  ka=(a[0],a[1],a[2],a[3]==tgt(a));kb=(b[0],b[1],b[2],b[3]==tgt(b))
  assert (tb[a]==tb[b])==(ka==kb)
print("INDEPENDENT CLAIM-STATE VALIDATION: PASS")
print("E3b refinement counts:",ec)
print("Thermostat refinement counts:",tc)
