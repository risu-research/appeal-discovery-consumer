# E3b same-object certificate-binding fast path

Status: optimization increment; no new ReplayMark semantics.

## Scientific boundary

ReplayMark's paper question remains: when may a historical decision still stand for what the target would have done? This increment does not change the answer, the three-valued verdicts, R*, claim projection, evidence semantics, realization, same-task correlation, or execution policy. It is a bounded artifact-feasibility refinement after the scientific chain was already frozen.

The post-optimization residual profile showed that construction of `E3bShadowRuntimeReuseCertificate` still spent roughly 59–60 us p50, much of it reserializing and hashing realized values that the production bridge passes by exact object identity.

## Optimization

The production bridge constructs `RuntimeReuseCertificate` with exactly:

- `observation = correlated_pair.observation`
- `historical_action = correlated_pair.historical_action`

and immediately embeds that semantic certificate beside the same `correlated_pair` in the E3b wrapper. `RealizedObservation` and `RealizedHistoricalAction` are frozen value objects.

Therefore wrapper-local equality is already established when the two references are the same object. The wrapper now uses:

```python
if semantic.observation is not pair.observation:
    compare content fingerprints

if semantic.historical_action is not pair.historical_action:
    compare content fingerprints
```

This is not caller self-certification. The caller cannot supply a boolean identity claim; Python object identity is observed directly by the wrapper.

## Fail-closed detached path

Reloaded, copied, reconstructed, or otherwise detached objects are not identity hits. They retain the pre-optimization content-addressed comparison exactly. A detached value with different content is rejected.

Thus the optimization has two modes:

1. exact same frozen object -> equality is tautological, no redundant rehash;
2. different object -> original fingerprint equality requirement.

## Required gates

Promotion requires all of the following, independent of speed:

- exact optimization parent and one atomic child commit;
- no production changes outside `replaymark/runtime_e3b_bridge.py`;
- bridge semantic digest unchanged;
- same-object wrapper performs zero realized-value fingerprint calls;
- byte-identical detached values perform the original four fingerprint calls and remain accepted;
- detached mismatched values fail closed;
- VALID, INVALID, and UNRESOLVED certificate bytes remain stable;
- previous contract-identity optimization safety gate remains PASS;
- existing semantic, realization, correlation, adjudication, R*, and bridge gates remain PASS;
- live Mosquitto R1 noninterference remains PASS;
- 192-row Integrated Frozen Runtime Conformance remains PASS;
- 128-case parent-vs-fast-path live-corpus certificate bytes are exact;
- post-fast-path residual cost profile remains measurement-valid.

No latency threshold is a promotion condition.

## Paper role

This optimization is evidence that the proof-carrying runtime can be engineered without weakening its scientific boundary. It should not become a paper contribution by itself and should not displace the central result: safe reuse is determined by semantic support under available evidence, not by replaying historical timing or bytes alone.

Execution/fallback remains NOT_IMPLEMENTED in this increment.
