# Gate S3 — First-Complete Caller-Owned Native Restoration Execution

Status: **EXECUTION IMPLEMENTATION FROZEN BEFORE FIRST S3 TARGET EXPOSURE.**

This increment implements the already-frozen S3-P protocol without changing ReplayMark production semantics or the P6 heterogeneous target.

## Authority

- S3-P protocol: `75d5d4379fdda221c0b9661f799d7779d6bba9f2`
- S2-F result seal: `313d24099546eb672eeabb5d449a476b261087be`
- exact P6 target blob: `5b57bc44e91dc38e44eaafc760286fa4b616ff9c`
- execution admission remains no-fallback.

## Execution discipline

Each trial first freezes all 192 observations and passes the A-side quiescence barrier. It then constructs and certifies all 192 historical ACT2 candidates before any policy-dependent traffic. Only after the certification barrier are caller policies executed.

The three policies are the fixed P6 partition relabeled prospectively by S3-P:

```text
ALWAYS_REUSE
ALWAYS_NATIVE
REPLAYMARK_NATIVE
```

No hidden target-class schedule is present in the live runner.

## Separate provenance channels

Historical reuse is recorded only through `HISTORICAL_ACT2`.
Caller-native recovery is recorded only through:

```text
NATIVE_QUERY_A
NATIVE_FRESH_ACT2
```

The ReplayMark execution gate receives only the historical recorder as its sink. It cannot invoke either native channel.

For every caller-native task the runner records the exact causal chain:

```text
NATIVE_QUERY_A publish
< query-caused same-task A confirmation
< fresh ACT2 generation
<= NATIVE_FRESH_ACT2 publish
< matching B-side command effect
```

No automatic retry is implemented. Query, fresh-ACT2, execution-gate, or B-effect failures remain distinct failures and do not change ReplayMark's semantic verdict.

## First-complete authority rule

The workflow preflight must pass before the broker or target is started. A preflight-only development failure is not a scientific target result. Once the first complete 1,152-row S3 live report exists, that report is authoritative whether PASS or FAIL and may not be replaced by a later favorable rerun.

## Independent promotion verifier

The post-run verifier uses only the Python standard library. It independently reconstructs:

- the inherited P6 task-policy partition;
- the hidden P6 target-class schedule for evaluation only;
- semantic safety from raw observation/action bytes;
- historical/native execution sets from the disjoint application provenance channels;
- query-confirmation-to-fresh-ACT2 causal binding;
- B-side restoration effects;
- exact safe-history/native-complement equalities required by S3-P.

Latency does not participate in promotion.
