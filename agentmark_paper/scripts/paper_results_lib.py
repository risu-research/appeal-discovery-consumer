#!/usr/bin/env python3
"""Fail-closed canonical paper-results layer for AgentMark."""
from __future__ import annotations
import hashlib, json
from fractions import Fraction
from pathlib import Path
from typing import Any

class ValidationError(RuntimeError): pass
def req(x: bool, m: str) -> None:
    if not x: raise ValidationError(m)
def readj(p: Path) -> dict[str, Any]:
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e: raise ValidationError(f"cannot parse {p}: {e}") from e
def cjson(x: Any) -> str: return json.dumps(x, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_file(p: Path) -> str: return sha_bytes(p.read_bytes())

# Independent trust anchor: immutable successful-run identities verified against GitHub Actions.
IMMUTABLE = {
 "e3b": (33935626964,"5f5eb578f2d47de8e8ac53c1dacee917c49cd9dd",9960088059,
         "829e05748ae38c76f880ab57538112a980c1da3d3ebedd4b84c1e6409093eb95",
         "46d0ef0c82cf1fd40c3746cffb667d101d32a5431e7b52f99a9fa7fecf323b12",
         "agentmark.e3b.r0_r1_r2_certificate.v2"),
 "e3c":(33942887473,"02028046d3f3d4fc32ed44b15c4b986e9df3545a",9962430737,
         "7ef5140a6dcdaee508154d49071aa15733da95b7507ead7d8d63afc963a12cb3",
         "9e1e91d4e7733880da8236b3a4afb3647f8aa9582fe8f7d6d2a8ec44f038653b",
         "agentmark.e3c.home_assistant.replicated_aggregate.v1"),
 "n1":  (33946985750,"5b2ba2aa35bf0bd00715b6b9475b44d9695c3c8f",9963663630,
         "14dfde9ff11865a548984ec4858429258d2d4fc1b7584c41d96a251530eb3f27",
         "4812816bd830b5e71d89843f8510c44f93c37a89b054ae8ef7a9358e90ec00f7",
         "agentmark.natural_controller.motion_light.replicated.v1"),
 "n2":  (33965918153,"4264c43d013178c8babedf772b1c06c5ddbe73cb",9969439579,
         "76bd2850156040139aabd935ccab44f01fb27344770c2f04a055fed81ee901b7",
         "df389a937832374008e459afd2a0454e632675a713b0a3b2b7d1b9258894d446",
         "agentmark.natural_controller.better_thermostat.replicated.v4"),
 "n2b": (33972619262,"9ec25a1cc2a16bff893d7ff5ffc9271bf6e059f6",9971397583,
         "4d75b17e6bd0bd9ba41cb574f9bca022364c312c09b215b74a36a92fda5861db",
         "93975a490a6af4e48e35152a77129430df0b0f7883015fc2ce72bd0d6fdffe75",
         "agentmark.n2b.replicated_aggregate.v2"),
}
def ec(v:int,u:str)->dict: req(type(v) is int,"exact count must be int"); return {"kind":"exact_count","value":v,"unit":u}
def es(v:int,l:str)->dict: req(v in (0,1),f"{l} must be exact 0/1"); return {"kind":"exact_scalar","label":l,"value":v}
def ef(n:int,d:int,l:str)->dict:
    req(type(n) is int and type(d) is int and d>0,"bad exact fraction")
    f=Fraction(n,d); return {"kind":"exact_fraction","label":l,"numerator":f.numerator,"denominator":f.denominator,"decimal":float(f)}
def emp(n:int,d:int,l:str)->dict:
    req(type(n) is int and type(d) is int and 0<=n<=d and d>0,"bad empirical fraction")
    return {"kind":"empirical_fraction","label":l,"successes":n,"trials":d,"decimal":float(Fraction(n,d))}
def ms(v:float,l:str,r:int|None=None)->dict:
    req(type(v) in (int,float),f"{l} not numeric"); o={"kind":"measured_ms","label":l,"value":float(v),"unit":"ms"}
    if r is not None:o["replica"]=r
    return o

def load_validate(root:Path)->dict:
    p=root/"CANONICAL_EVIDENCE.json"; d=readj(p)
    req(d.get("schema")=="agentmark.paper_canonical_evidence.v1","evidence schema drift")
    req(d.get("status")=="SEALED_PAPER_ADMITTED_EVIDENCE","evidence status drift")
    req(d["source_snapshot"]["head"]=="1a38808a2c83fb6cf68091beb0a244eec3dab9ec","source snapshot drift")
    req(d["policy"]["narrative_memory_is_source"] is False,"narrative memory cannot be authoritative")
    g=d["governance"]; req(g["empirical_stop_active"] is True,"empirical stop deactivated")
    v1=[x for x in g["excluded"] if x["id"]=="N2b-v1"]
    req(len(v1)==1 and v1[0]["run_id"]==33972326066 and v1[0]["canonical"] is False,"N2b v1 re-admitted")
    bd=[x for x in g["excluded"] if x["id"]=="E3b-safety-boundary"]
    req(len(bd)==1 and bd[0]["artifact_id"]==9960095929 and bd[0]["canonical_headline"] is False,"E3b boundary leaked into headline")
    for k, vals in IMMUTABLE.items():
        e=d["evidence"][k]; p=e["provenance"]
        actual=(p["run_id"],p["execution_commit"],p["artifact_id"],p["archive_sha256"],p["source_primary_sha256"],p["source_schema"])
        req(actual==vals,f"{k}: immutable Actions/source provenance drift")
    return d

def build(root:Path)->dict:
    d=load_validate(root); E=d["evidence"]
    a=E["e3b"]["result"]; req(a["decision"]=="PROMOTED" and a["decisive_trials"]==12,"E3b decision/trial drift")
    req(a["native_publish_per_trial"]=={"R0":512,"R1":512,"R2":768},"E3b native PUBLISH drift")
    req(a["support_failures"]=={"R0":12,"R1":12,"R2":0} and a["verify_trials_R2"]==12,"E3b semantics drift")
    req(a["safety_certificate"]["classification"]=="CERTIFIED_UNSAFE" and a["safety_certificate"]["eta"]==1,"E3b safety certificate drift")
    b=E["e3c"]["result"]; req(b["decision"]=="PROMOTED_REPLICATED" and b["replicas"]==2 and b["validation_passes"]==2,"E3c promotion drift")
    req(b["native_work_per_trial"]=={"R0":256,"R1":256,"R2":384},"E3c native work drift")
    req(b["support_failures"]=={"R0":1536,"R1":1536,"R2":0} and b["verify_rows_R2"]==1536,"E3c semantics drift")
    req(len(b["source_completion_p99_ms_by_replica"])==2,"E3c timing replica separation lost")
    c=E["n1"]["result"]; req(c["decision"]=="PROMOTED_REPLICATED" and c["replicas"]==[0,1] and c["validation_passes"]==2,"N1 promotion drift")
    req(c["trials_per_mode_total"]==12 and c["support_failures"]=={"R0":12,"R1":12,"R2":0},"N1 trial/semantics drift")
    rt=c["runner_timing_ms"]; req([x["replica"] for x in rt]==[0,1],"N1 timing replicas lost")
    req(rt[0]["R1_minus_R0"]==35.24896700000001 and rt[1]["R1_minus_R0"]==35.178532166666656,"N1 canonical timing drift")
    n2=E["n2"]["result"]; req(n2["decision"]=="PROMOTED_REPLICATED" and n2["replicas"]==[0,1] and n2["validation_passes"]==2,"N2 promotion drift")
    req((n2["TV_operation"],n2["TV_action"])==(0,1),"N2 TV drift")
    req(n2["source_action"]["operation"]==n2["target_action"]["operation"]=="climate.set_preset_mode","N2 operation drift")
    req(n2["source_action"]["variant"]=='{"preset_mode":"home"}' and n2["target_action"]["variant"]=='{"preset_mode":"away"}',"N2 action variants drift")
    req(n2["observer_ordering_diagnostics_used_for_promotion"] is False,"N2 diagnostic accidentally promoted")
    q=E["n2b"]["result"]; req(q["decision"]=="PROMOTED_REPLICATED" and q["replicas"]==[0,1] and q["validation_passes"]==2,"N2b promotion drift")
    req((q["raw_feedback_TV"],q["quotient_feedback_TV"],q["TV_operation"],q["TV_action"],q["pair_restricted_eta_action"])==(1,0,0,0,0),"N2b theory drift")
    req(q["counts"]=={"source_native":12,"target_native":12,"target_replay":12,"no_shift_replay":12,
      "target_replay_action_support_failures":0,"control_replay_action_support_failures":0},"N2b counts drift")
    req(q["unsupported_feedback"]==[] and q["measurement_contract"]["v1_failure_run"]==33972326066,"N2b support/measurement drift")

    prov={k:{**E[k]["provenance"],"canonical":True} for k in IMMUTABLE}
    return {
      "schema":"agentmark.paper_results_manifest.v1","status":"FROZEN_CANONICAL",
      "canonical_evidence_sha256":sha_file(root/"CANONICAL_EVIDENCE.json"),
      "generation_policy":{"machine_owned":True,"source":"CANONICAL_EVIDENCE.json only","narrative_memory_is_authoritative":False,
                           "exact_vs_measured_type_separation":True},
      "evidence":prov,
      "headline_results":{
        "timing_fidelity_is_not_controller_semantic_fidelity":{
          "state":"CLOSED","evidence":["e3b","e3c","n1"],
          "e3b":{"R0":emp(12,12,"support failures"),"R1":emp(12,12,"support failures"),"R2":emp(0,12,"support failures")},
          "e3c":{"R0":emp(1536,1536,"support failures"),"R1":emp(1536,1536,"support failures"),"R2":emp(0,1536,"support failures")},
          "n1":{"R0":emp(12,12,"support failures"),"R1":emp(12,12,"support failures"),"R2":emp(0,12,"support failures")}},
        "replay_semantics_can_change_benchmark_workload":{
          "state":"CLOSED","evidence":["e3b","e3c"],
          "e3b":{"work":{"R0":ec(512,"broker PUBLISH"),"R1":ec(512,"broker PUBLISH"),"R2":ec(768,"broker PUBLISH")},
                 "R2_over_R1":ef(768,512,"native broker-PUBLISH workload ratio")},
          "e3c":{"work":{"R0":ec(256,"native HA service calls"),"R1":ec(256,"native HA service calls"),"R2":ec(384,"native HA service calls")},
                 "R2_over_R1":ef(384,256,"native Home Assistant workload ratio")}},
        "operation_identity_is_not_action_identity":{"state":"CLOSED","evidence":["n2"],"TV_operation":es(0,"operation TV"),"TV_action":es(1,"action TV"),
                 "source_action":n2["source_action"],"target_action":n2["target_action"]},
        "raw_feedback_difference_is_not_replay_invalidity":{"state":"CLOSED","evidence":["n2b"],
                 "raw_feedback_TV":es(1,"raw feedback TV"),"quotient_feedback_TV":es(0,"decision-quotient feedback TV"),
                 "TV_operation":es(0,"operation TV"),"TV_action":es(0,"action TV"),"pair_restricted_eta_action":es(0,"pair-restricted eta"),
                 "target_replay_support_failures":emp(0,12,"action-support failures")}},
      "measured_timing":{
        "e3b":{"R1_shift_vs_R0":ms(a["timing_ms"]["R1_shift_vs_R0"],"aggregate R1 shift vs R0"),
               "R0_p99":ms(a["timing_ms"]["R0_p99"],"R0 p99"),"R1_p99":ms(a["timing_ms"]["R1_p99"],"R1 p99"),"R2_p99":ms(a["timing_ms"]["R2_p99"],"R2 p99")},
        "e3c":{"source_completion_p99_by_replica":[ms(x,"source completion p99",i) for i,x in enumerate(b["source_completion_p99_ms_by_replica"])],
               "R1_mean_act2_shift_vs_source":ms(b["mean_act2_shift_vs_source_ms"]["R1"],"R1 mean act2 shift vs source"),
               "R2_mean_act2_shift_vs_source":ms(b["mean_act2_shift_vs_source_ms"]["R2"],"R2 mean act2 shift vs source")},
        "n1":{"policy":"replica values remain separate; no canonical cross-runner average",
              "timing_by_replica":[{"replica":x["replica"],"R1_minus_R0":ms(x["R1_minus_R0"],"R1 minus R0 mean",x["replica"]),
                                    "R2_minus_source":ms(x["R2_minus_source"],"R2 minus source mean",x["replica"])} for x in rt]}},
      "claim_boundaries":{"e3c":b["claim_boundary"],"n2":n2["claim_boundary"],
                          "n2b":"pair-restricted eta=0 is not a claim that the full Better Thermostat controller is feedback-insensitive."},
      "governance":{"empirical_stop_active":True,"excluded_evidence":d["governance"]["excluded"],
                    "rule":"No new generic empirical system unless adversarial paper review exposes a specific undefended claim."}
    }

def typecheck(m:dict)->None:
    w=m["headline_results"]["replay_semantics_can_change_benchmark_workload"]
    for k in ("e3b","e3c"):
        r=w[k]["R2_over_R1"]; req(r["kind"]=="exact_fraction" and (r["numerator"],r["denominator"],r["decimal"])==(3,2,1.5),f"{k} exact workload ratio corrupted")
        req(all(x["kind"]=="exact_count" for x in w[k]["work"].values()),f"{k} workload count type corrupted")
    def walk(x):
        if isinstance(x,dict):
            if "kind" in x: yield x
            for v in x.values(): yield from walk(v)
        elif isinstance(x,list):
            for v in x: yield from walk(v)
    req(not any(x["kind"]=="measured_ms" for x in walk(w)),"measured timing leaked into exact workload")
    n=m["measured_timing"]["n1"]; req([x["replica"] for x in n["timing_by_replica"]]==[0,1],"N1 canonical timing was averaged/collapsed")
    req(all(x["R1_minus_R0"]["kind"]=="measured_ms" and x["R2_minus_source"]["kind"]=="measured_ms" for x in n["timing_by_replica"]),"N1 timing type corruption")

def mhash(m:dict)->str:return sha_bytes(cjson(m).encode())
