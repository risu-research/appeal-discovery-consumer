# AgentMark E3c — Home Assistant Ecological-Validity Preregistration

Status: **FROZEN BEFORE THE FIRST E3c RUN**

E3c asks one narrow question: does the E3b replay-semantic separation survive when the middleware substrate is Home Assistant Core rather than the dedicated MQTT harness?

This gate does **not** reopen the rejected E3b 80 ms endogeneity hypothesis. It is an ecological replication of the promoted R0/R1/R2 claim.

## Frozen substrate

- Home Assistant Core image tag resolved once, then both independent runner replicas execute the exact resolved digest.
- Required HA Core semantic layer: `ServiceRegistry`, `EVENT_CALL_SERVICE`, `StateMachine`, `EVENT_STATE_CHANGED`, and `Context` propagation.
- AgentMark kernel/certificate implementation is reused from the E3b branch; no E3c-specific certificate math is substituted.
- Device behavior is deterministic and virtual. This is a middleware ecological-validity test, not a physical radio/device claim.

## Frozen controller

Decision deadline: **100 ms** after ACT1 issue.

At the decision state:

- `VISIBLE` by 100 ms -> next semantic operation `ACT2`.
- `MISS` at 100 ms -> next semantic operation `VERIFY`, then `ACT2`.

The controller is deterministic and feedback-sensitive (`eta(K)=1` at the decision state).

## Frozen environment contrast

- source device visibility delay: **35 ms**;
- target device visibility delay: **180 ms**;
- tasks per source/target batch: **128**;
- wave size: **32**;
- wave launch period: **300 ms**;
- target trials per independent runner replica: **6**;
- independent runner replicas: **2**;
- total decisive target trials if both replicas are valid: **12**.

Source traces are recorded first on each independent runner. The 100 ms controller deadline and target delay are not recalibrated from target outcomes.

## Replay ladder

### R0 — rigid

Reissue ACT1 and recorded ACT2 at the source task's recorded issue timing. Semantic identity and issue timing are frozen.

### R1 — timing-feedback-only

Issue ACT1, wait for current-target service completion, preserve the source post-completion think time, then reissue the recorded ACT2. Semantic operation identity remains frozen.

### R2 — semantic feedback-preserving

Issue ACT1 and observe the actual HA entity state through `state_changed`. At 100 ms, branch using current feedback. On `MISS`, issue VERIFY and only then ACT2.

## Native accounting invariants

The primary workload counter is Home Assistant's own `EVENT_CALL_SERVICE` stream for the experiment domain.

For every decisive trial, exact conservation is required:

- R0: `128 * 2 = 256` service-call events;
- R1: `128 * 2 = 256` service-call events;
- R2: `128 * 3 = 384` service-call events.

Therefore the decisive semantic workload ratio must be exactly:

`W_R2 / W_R1 = 1.5`.

The experiment also requires every ACT1/ACT2-generated `state_changed` event to carry the exact Home Assistant `Context.id` of its causative service call.

## Promotion gates

E3c is promoted only if **all** of the following hold in both independent runner replicas:

1. source trace is valid: all ACT1 completions occur before the frozen 100 ms deadline;
2. target decisive feedback is `MISS` for every task in R0/R1/R2;
3. R0 support violation = 100%;
4. R1 support violation = 100%;
5. R1 materially changes ACT2 issue timing: mean shift >= `max(25 ms, 0.5*(target-source delay))`;
6. R2 support violation = 0%;
7. R2 VERIFY fraction = 100%;
8. native HA service-call conservation is exact in every trial;
9. R2/R1 native workload ratio is exactly 1.5 in every trial;
10. HA Context lineage matches 100% for causally attributable ACT1/ACT2 state changes;
11. the feedback-sensitive Replay Safety Certificate is not safe at epsilon=0.05, confidence=0.95;
12. no-feedback-shift negative control produces zero support violation and no VERIFY for all modes;
13. feedback-insensitive negative control produces zero support violation, no VERIFY, equal R0/R1/R2 workload, and a safe certificate;
14. an independent post-run validator recomputes the gates from raw replay rows and raw HA event streams;
15. both independent runner replicas pass before the combined artifact can say `PROMOTED_REPLICATED`.

R0 issue timing is additionally required to remain within 35 ms absolute per-task deviation from its paired recorded source ACT2 issue time. This is a validity bound, not an effect-size claim.

## Forbidden post-hoc moves

After the first E3c run begins, do not:

- move the 100 ms deadline;
- change 35/180 ms delays to rescue a result;
- relax exact call-service conservation;
- ignore a failed independent replica;
- replace Context lineage with client-side guessed attribution;
- redefine R1 to allow semantic operation changes;
- remove either negative control;
- downgrade the 1.5x exact conservation requirement to an approximate ratio;
- promote a physical-device, MQTT, Matter, radio, or energy claim from this test.

If a measurement or implementation bug is found, mark the affected run invalid, document the fix, and rerun the frozen scientific protocol. Do not reinterpret the invalid run as evidence.
