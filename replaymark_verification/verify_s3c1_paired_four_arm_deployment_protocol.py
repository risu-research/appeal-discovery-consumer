from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path

PARENT="94584db84bebd73e664f19f0fe2d3b9f5998c813"
PTREE="4b23ec476b4613d7e5688865deb4963d709b414d"
SEED="replaymark.s3c1.paired-target-class.v1|c0="+PARENT
SCHED="3330c82c66cd344e01b48ac16e96e5fb4b4cb3a6b55ea880fe6285621e039af8"
PATHS={
 ".github/workflows/replaymark-runtime-gate-s3c1-paired-four-arm-deployment-protocol.yml",
 "replaymark/S3C1_PAIRED_FOUR_ARM_DEPLOYMENT_PROTOCOL.json",
 "replaymark/S3C1_PAIRED_FOUR_ARM_DEPLOYMENT_PROTOCOL.md",
 "replaymark_verification/verify_s3c1_paired_four_arm_deployment_protocol.py",
}
BLOBS={
 ("HEAD","replaymark/S3C0_CLAIM_TO_QUEUE_COMPOSITION_RESULT_SEAL.json"):"6590883c26977cc66487e7111097ec0a6b3266db",
 ("HEAD","replaymark/S3_CALLER_OWNED_NATIVE_RESTORATION_RESULT_SEAL.json"):"35658806601f84a67199cd691607d0ead388952b",
 ("HEAD","agentmark_e3b_lab/e3_mqtt/app/replaymark_s3_caller_native_restoration.py"):"cd4150585e36c07b737e27e5a879030b031dab4f",
 ("HEAD","agentmark_e3b_lab/e3_mqtt/app/s2p6_heterogeneous_device.py"):"5b57bc44e91dc38e44eaafc760286fa4b616ff9c",
 ("HEAD","replaymark/runtime_e3b_execution_gate.py"):"22748a5aa820e83e4700a339e8af297cdd9f9143",
 ("HEAD","replaymark/runtime_e3b_action.py"):"d5d483751eb06fd8b00f7bb2eff613a20f0f796c",
 ("HEAD","replaymark/runtime_e3b_observation.py"):"de6cdc8ccdbb9b189e238cc5dbad173060fe17ab",
 ("HEAD","replaymark/runtime_e3b_correlation.py"):"bbdc243eccf29c0a26b92bc78c0acdb96222da8e",
 ("HEAD","replaymark/runtime_e3b_bridge.py"):"5c2b13f35edcae9ce42fa062f51f1b6ce46747bf",
 ("23b7c85bca6cb85fde9f4361a0f9664d21c8ae8d","replaymark_e3b_default_flip/DEFAULT_FLIP_PROTOCOL.md"):"d05917bf9ad69edb8adf1a642efda598b9b2aa0e",
 ("ac20890bb4aa926e439802510de3723b74591c94","replaymark_e3b_default_flip/CONFIRMATORY_OUTCOME.md"):"6d9c90d629b0e384b568a25fa93504dbe23828e6",
}
def g(*a): return subprocess.check_output(["git",*a],text=True).strip()
def sha(b): return hashlib.sha256(b).hexdigest()
def schedule(bs,trials):
    rows=[]; bal={}
    for n in bs:
        for t in range(trials):
            ranked=sorted((sha(f"{SEED}|batch={n}|trial={t}|task={i}".encode()),i) for i in range(n))
            shifted={i for _,i in ranked[:n//2]}
            bal[f"{n}:{t}"]=(len(shifted),n-len(shifted))
            rows += [{"batch_size":n,"trial":t,"task_id":i,
                      "class":"SHIFTED" if i in shifted else "REFERENCE"} for i in range(n)]
    return rows,bal

def main():
    if len(sys.argv)!=3 or sys.argv[1]!="--out": raise SystemExit("usage: verifier --out PATH")
    pth=Path("replaymark/S3C1_PAIRED_FOUR_ARM_DEPLOYMENT_PROTOCOL.json")
    p=json.loads(pth.read_text())
    c={}; d={}
    c["exact_parent"]=g("rev-parse","HEAD^")==PARENT
    c["parent_tree"]=g("show","-s","--format=%T","HEAD^")==PTREE
    changed=set(filter(None,g("diff","--name-only","HEAD^","HEAD").splitlines()))
    c["four_files_only"]=changed==PATHS; d["changed_paths"]=sorted(changed)

    br=[]
    for (ref,path),exp in BLOBS.items():
        act=g("rev-parse",f"{ref}:{path}")
        br.append({"ref":ref,"path":path,"expected":exp,"actual":act,"match":act==exp})
    c["all_frozen_blobs_exact"]=all(x["match"] for x in br); d["blobs"]=br

    c["schema_status"]=p["schema"]=="replaymark.s3c1-paired-four-arm-deployment-closure-protocol.v1" and p["status"]=="FROZEN_BEFORE_IMPLEMENTATION_OR_QUEUE_EXECUTION"
    a=p["authority"]; c["authority_exact"]=a["exact_parent_s3c0_result_seal"]==PARENT and a["parent_tree"]==PTREE
    q=p["queue_endpoint"]
    c["queue_authority"]=(
      q["broker"]=="Eclipse Mosquitto 2.1.2" and
      q["broker_image_digest"]=="sha256:6f8d8a947c506f8a2290ec65cd4bd2bc7cb4d43fb5f6271f861cb013e2ef9797" and
      q["documented_default_max_queued_messages"]==1000 and q["documented_default_max_queued_bytes"]==0 and
      q["canonical_config_sha256"]=="886f26936b560ebfbf584744c8c4f5f2dd3eeeba946313ad1d2f7f8848bf0858" and
      q["queue_policy_override"] is False and q["measured_qos"]==1 and
      q["measured_terminal_roles"]==["command","query","state"])
    c["queue_isolation"]=all(q[k] is True for k in
      ["one_isolated_persistent_client_per_arm","explicit_device_filter_set_per_arm",
       "broad_cross_arm_subscription_forbidden","fresh_broker_and_empty_state_per_paired_cell"])

    x=p["paired_four_arm_design"]
    c["arms_exact"]=x["arms"]==["ALWAYS_REUSE","DIRECT_NATIVE","REPLAYMARK_NATIVE","ALWAYS_NATIVE"]
    c["direct_is_truth_not_rerun_all"]=(x["DIRECT_NATIVE"]["role"]=="primary deployment truth" and
      x["DIRECT_NATIVE"]["imports_replaymark"] is False and x["DIRECT_NATIVE"]["uses_certificate"] is False and
      x["DIRECT_NATIVE"]["uses_historical_act2"] is False and "not deployment truth" in x["ALWAYS_NATIVE"]["role"])
    c["work_laws"]=(
      x["ALWAYS_REUSE"]["work_law"]["total"]=="4N" and
      x["DIRECT_NATIVE"]["work_law"]["total"]=="4N+2U" and
      x["REPLAYMARK_NATIVE"]["work_law"]["total"]=="4N+2U" and
      x["ALWAYS_NATIVE"]["work_law"]["total"]=="6N")
    f=p["frozen_semantic_boundary"]
    c["replaymark_semantics_frozen"]=(f["replaymark_semantic_core_modified"] is False and
      f["runtime_realizers_modified"] is False and f["s1_execution_gate_modified"] is False and
      f["historical_act2_template_modified"] is False and f["fallback_inside_replaymark"] is False and
      f["regeneration_inside_replaymark"] is False and f["automatic_retry"]=="ABSENT")

    w=p["target_workload"]; tc=w["target_implementation_contract"]
    c["paired_barrier"]=w["logical_wave_size"]==4 and w["physical_four_arm_twins_per_wave"]==16 and w["wave_period_ms"]==500.0 and w["verify_deadline_ms"]==100.0 and w["reference_delay_ms"]==0 and w["shifted_delay_ms"]==180 and w["evidence_mismatch_never_truncates_workload"] is True and w["no_post_hoc_task_exclusion"] is True
    c["target_generalization_bounded"]=(tc["additive_lab_only"] is True and tc["mechanism_matches_frozen_p6_command_query_state_semantics"] is True)
    c["target_no_forbidden_inputs"]=all(tc[k] is True for k in ["no_policy_input","no_certificate_input","no_replaymark_import","no_oracle_input","no_runtime_adaptation"]) and tc["class_label_on_wire"] is False

    l=p["stress_ladder"]; center=int(1000/5); offs=[-8,-4,0,4,8]; bs=[center+i for i in offs]
    c["stress_center"]=center==200 and l["nominal_stress_center_tasks"]==200
    c["ladder_mechanical"]=(l["offsets_from_center"]==offs and l["batch_sizes"]==bs==[192,196,200,204,208] and
      166 not in bs and l["legacy_166_boundary_inherited"] is False and l["hardcode_166"] is False and l["no_preselected_native_boundary"] is True)
    nom=[{"batch_size":n,"nominal_U":n//2,"ALWAYS_REUSE":4*n,"DIRECT_NATIVE":5*n,"REPLAYMARK_NATIVE":5*n,"ALWAYS_NATIVE":6*n} for n in bs]
    c["nominal_table"]=l["nominal_counts"]==nom
    c["two_sided_stress_anchors"]=5*min(bs)<1000<5*max(bs) and all(4*n<1000 for n in bs) and all(6*n>1000 for n in bs)

    s=p["target_class_schedule"]; rows,bal=schedule(s["batches"],s["trials"])
    ssha=sha(json.dumps(rows,sort_keys=True,separators=(",",":")).encode())
    c["schedule_digest"]=s["seed"]==SEED and ssha==SCHED and s["canonical_schedule_sha256"]==SCHED
    c["schedule_balance"]=all(a==b for a,b in bal.values()) and s["exact_half_shifted_each_cell"] is True
    c["schedule_blind"]=all(s[k] is True for k in ["same_class_for_all_four_arm_twins","policy_blind","certificate_blind","outcome_blind"])
    d["schedule_sha256"]=ssha

    r=p["replication"]
    c["replication_exact"]=(r["hosted_replicas"]==["A","B"] and r["trials_per_batch_per_replica"]==6 and
      r["paired_cells_total"]==60 and r["logical_rows_per_replica"]==6000 and r["logical_rows_total"]==12000 and
      r["arm_task_executions_total"]==48000 and r["all_cells_required"] is True and r["early_stop"] is False)

    ap=p["anti_leakage_and_pairing"]
    c["pairing_fail_closed"]=all(ap[k] is True for k in
      ["direct_and_replaymark_evidence_token_equality_required_taskwise","mismatch_is_gate_failure_not_exclusion",
       "direct_reference_may_not_import_replaymark_runner_or_production","replaymark_may_not_read_hidden_class",
       "runner_may_not_read_independent_oracle_result_before_dispatch","queue_outcome_may_not_change_any_parameter",
       "target_class_may_not_depend_on_arm","target_class_may_not_depend_on_policy"])
    o=p["independent_validation"]
    c["independent_oracle"]=(o["runs_after_all_live_dispatch_and_all_queue_drains_for_cell"] is True and
      o["imports_replaymark_production"] is False and o["imports_live_runner"] is False and
      o["trusts_runner_summary_fields"] is False and o["hidden_target_class_is_semantic_truth"] is False)

    pc=p["promotion_criteria"]; prim="\n".join(pc["primary"]); neg="\n".join(pc["decisive_negative_controls"])
    c["primary_cellwise_equality"]=("every cell" in prim and "historical reuse set equals independent safe-evidence set" in prim and "unsafe historical executions=0" in prim and pc["all_required"] is True)
    c["two_sided_negative_controls"]=("ALWAYS_REUSE=LOSSLESS" in neg and "ALWAYS_NATIVE=LOSSY" in neg and neg.count("within each hosted replica")==2)
    c["frontier_bounded"]=pc["secondary_tested_frontier"]["direct_native_equals_replaymark_native"] is True and pc["secondary_tested_frontier"]["global_capacity_claim"] is False

    fa=p["failure_authority"]
    c["first_complete_immutable"]=(fa["first_complete_full_matrix_and_validator_certificate_is_authoritative"] is True and
      fa["scientific_mismatch_is_preserved"] is True and fa["later_exact_runs_are_replication_only"] is True and
      all(fa[k] is False for k in ["same_generation_retune","batch_substitution_after_outcome","deadline_retune",
       "delay_retune","wave_retune","queue_retune","drop_failed_cell"]))
    b=p["c1_protocol_boundary"]
    c["protocol_only"]=b["protocol_only"] is True and all(b[k] is False for k in
      ["experiment_runner_added","target_implementation_added","queue_execution_permitted","target_outcomes_visible","result_file_added"])
    c["no_live_code_added"]=[z for z in changed if z.endswith(".py") and z not in
      {"replaymark_verification/verify_s3c1_paired_four_arm_deployment_protocol.py"}]==[]
    wf=Path(".github/workflows/replaymark-runtime-gate-s3c1-paired-four-arm-deployment-protocol.yml").read_text().lower()
    c["workflow_no_target_execution"]=not any(t in wf for t in ["docker run","docker compose","mosquitto_pub","mosquitto_sub","replaymark_s3c1_paired_device"])

    verdict="PASS" if all(c.values()) else "FAIL"
    report={"schema":"replaymark.s3c1-paired-four-arm-deployment-protocol-verification.v1",
      "head":g("rev-parse","HEAD"),"parent":g("rev-parse","HEAD^"),"protocol_sha256":sha(pth.read_bytes()),
      "checks":c,"detail":d,"derived":{"queue_count":1000,"stress_center":200,"batches":bs,
      "schedule_rows_per_replica":len(rows),"schedule_sha256":ssha,"paired_cells":60,
      "logical_rows_total":12000,"arm_task_executions_total":48000,"legacy_166_inherited":False},"verdict":verdict}
    out=Path(sys.argv[2]); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if verdict=="PASS" else 2
if __name__=="__main__": raise SystemExit(main())
