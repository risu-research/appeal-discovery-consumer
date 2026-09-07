# Gate S0 — Current Runtime Seal

Status: **FROZEN PENDING CI SEAL**

This gate does not add a ReplayMark semantic rule, execution policy, fallback path, or new optimization. It records the exact current runtime authority and makes that authority the immutable base for the selective-reuse intervention work that follows.

## Frozen authority

- authority commit: `25d317392b9ce6aaaedc190ef6aff8bc38d555b5`
- authority tree: `7f8349a10d884a212c3f7143dbd56e2b8cc13718`
- authority parent: `a1445ce1b03aa75b95b97f518f1d79227f2206f9`
- successful authority workflow run: `34144836504`
- sealed authority artifact: `10027299146`
- artifact SHA-256: `c75868eefed78f80f8a13483020b79938d852c5e0083be029e425956e57a5625`

`replaymark/CURRENT_RUNTIME_SEAL.json` is the machine-readable authority manifest. The seal verifier requires this commit to be the exact parent of the S0 seal increment and requires every listed semantic, runtime, R1-live, and independent-oracle blob to remain byte-identical.

## What is closed at S0

The following are frozen as the starting scientific/runtime state for the next phase:

1. semantic core, including bounded claim-predictive quotient, evidence semantics, support envelope, three-valued adjudication, and R*;
2. `ExplicitCompiledContract` and its concrete packaging/identity;
3. E3b raw observation realization;
4. E3b historical-action realization;
5. exact same-task correlation;
6. chained E3b runtime semantic certificate;
7. non-interfering R1 shadow integration;
8. integrated task-by-task frozen runtime conformance;
9. runtime cost characterization and the current post-optimization residual profile;
10. verified immutable contract-identity reuse and same-object certificate-binding fast path.

S0 deliberately does **not** implement execution admission, selective reuse, caller fallback, or regeneration.

## Optimization stop rule

Runtime micro-optimization is frozen after this gate.

It may be reopened only if a later selective-reuse capstone measures a material bottleneck on the frozen production path. Reopening requires all of the following before implementation:

- a predeclared measurement protocol;
- capstone evidence identifying the material bottleneck;
- a bounded additive optimization branch;
- revalidation of semantic identity and certificate-byte equivalence.

Speculative speedups, aesthetic cleanup, microbenchmark-only gains without capstone relevance, or a desire for a smaller latency number are not sufficient reasons to reopen optimization.

## Scientific boundary

S0 preserves the following distinction for the rest of the project:

- R* decides whether historical reuse is certified under the available evidence.
- R* is not a fallback or regeneration policy.
- realization failure is not semantic `UNRESOLVED`.
- no runtime execution output is allowed to affect the S0 certification evidence retrospectively.
- frozen E3b/R1 and prior controller experiments remain historical evidence; later integration must not rewrite their protocols or outcomes.

## CI promotion rule

S0 promotes only if the exact child increment:

1. changes only this document, the machine-readable manifest, the S0 verifier, and the S0 workflow;
2. confirms the exact frozen blobs against both `HEAD^` and `HEAD`;
3. reruns the frozen semantic and runtime verification chain;
4. reruns the real Mosquitto R1 non-interference experiment;
5. recreates the 192-row integrated conformance matrix;
6. reruns the current post-optimization runtime residual profile without performing an optimization;
7. emits a sealed artifact whose `GATE_STATUS` explicitly leaves execution/fallback/selective intervention unimplemented.

Performance values are observations, not promotion thresholds.

After CI promotion, this gate becomes **CLOSED / PASS** and all Gate S1 work should branch from the S0 seal commit while preserving the frozen production blobs unless an explicit correctness bug is discovered.
