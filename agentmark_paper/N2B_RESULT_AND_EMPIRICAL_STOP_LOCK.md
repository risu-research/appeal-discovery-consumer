# AgentMark — N2b Result Lock + Empirical Stop Rule

Status: **PROMOTED_REPLICATED** on `agentmark-n2b-decision-equivalence`.

This is a post-outcome result lock. The pre-outcome Claim–Evidence Matrix and `N2B_PREREGISTRATION.md` remain unchanged. The invalid v1 observer and its correction are preserved separately in `N2B_MEASUREMENT_CORRECTION.md`.

## 1. Canonical execution

Valid workflow:

- workflow: `AgentMark N2b Decision Equivalence v2`
- GitHub Actions run: `33972619262`
- execution commit: `9ec25a1cc2a16bff893d7ff5ffc9271bf6e059f6`
- conclusion: `success`
- exact HA image: `ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293`
- aggregate artifact ID: `9971397583`
- aggregate artifact archive digest reported by GitHub: `sha256:4d75b17e6bd0bd9ba41cb574f9bca022364c312c09b215b74a36a92fda5861db`
- aggregate JSON SHA-256: `93975a490a6af4e48e35152a77129430df0b0f7883015fc2ce72bd0d6fdffe75`
- root `CHECKSUMS.sha256` SHA-256: `44e1bcaff027d337bb4eb172f2cb71d7913dc993129e3cb3466f15427c0a3c22`
- root checksum manifest entries: `325`

Both raw replica capsules revalidated under their own portable manifests before aggregation, and the aggregate root checksum manifest revalidated after packaging.

## 2. Invalid v1 run retained, not promoted

The first workflow (`33972326066`) failed before producing a valid N2b result because Home Assistant eagerly completed the automation/service call before a caller-side post-`async_set` microstep snapshot could be captured. The scientific pair and expected action were not changed.

The correction was frozen in `N2B_MEASUREMENT_CORRECTION.md` before the valid v2 run. v2 observes immutable feedback entities at the presence-transition event, at the climate service-issue event, and after action completion; it does not claim a strict pre-handler climate-state snapshot.

## 3. Frozen natural-controller pair

Same independently authored Better Thermostat Lean controller as sealed N2:

- source feedback `y_A`: presence=`off`, motion=`off`, night=`off`, optional boost/eco/activity absent;
- target feedback `y_B`: presence=`off`, motion=`on`, night=`off`, optional boost/eco/activity absent;
- raw feedback vectors differ only in motion;
- both native conditions use the identical trigger dimension: presence `on -> off`;
- current preset before trigger: `sleep`;
- predicted and required action in both cases: `climate.set_preset_mode`, target class `climate`, semantic variant `{"preset_mode":"away"}`.

No feedback pair, projection, expected action, threshold, controller source, ownership boundary, or replication count was altered after outcome observation.

## 4. Exact replicated result

Aggregate decision: **`PROMOTED_REPLICATED`**.

Across two independent replicas, six trials per condition per replica:

| Condition | Exact action | Count | Action support failures |
|---|---|---:|---:|
| Source native `y_A` | `climate.set_preset_mode(away)` | 12/12 | n/a |
| Target native `y_B` | `climate.set_preset_mode(away)` | 12/12 | n/a |
| Source action replayed under target `y_B` | `climate.set_preset_mode(away)` | 12/12 | 0/12 |
| No-shift replay control under `y_A` | `climate.set_preset_mode(away)` | 12/12 | 0/12 |

Both independent validators returned `PASS`; every validator check was true; both producer decisions were `PROMOTED`; aggregate recomputation agreed exactly across replicas.

For all 24 native rows, the feedback vector recorded on the presence transition, on the climate service-issue event, and after action completion was identical within each trial. The transition witness preceded the service-issue witness in every row.

## 5. Exact theory prediction confirmed

For the preregistered two-symbol restricted kernel:

- raw feedback TV: **1.0**;
- action decision partition: `((AWAY_MOTION_OFF, AWAY_MOTION_ON),)`;
- quotient feedback TV: **0.0**;
- operation workload TV: **0.0**;
- action workload TV: **0.0**;
- pair-restricted action sensitivity `eta`: **0.0**;
- unsupported feedback symbols: none.

The pair-restricted `eta=0` is not a claim that the full Better Thermostat controller is feedback-insensitive.

## 6. Scientific conclusion

N2b closes the safe-side prediction identified before execution in the Claim–Evidence Matrix:

> **Different raw feedback does not imply a different replay workload. What matters is whether the target feedback crosses a controller decision-equivalence class at the declared action projection.**

This is the natural-controller counterweight to the positive failure witnesses:

- E3b/E3c/N1: feedback crosses a decision boundary; timing-aware replay can preserve the wrong/unsupported action;
- N2: the operation name stays the same while the consequential action variant changes (`TV_operation=0`, `TV_action=1`);
- **N2b: raw feedback changes while the consequential action does not (`TV_feedback=1`, quotient/action TV=0), and replay remains supported.**

Therefore AgentMark is empirically distinguishable from a detector that merely flags feedback change.

## 7. Claim–Evidence Matrix after N2b

| Headline claim | State after N2b | Decisive evidence |
|---|---|---|
| Timing fidelity is not controller-semantic fidelity | **Closed** | E3b, E3c, N1 |
| Operation identity is not necessarily action identity | **Closed** | N2 |
| Replay semantics can change benchmark workload | **Closed** | E3b/E3c exact 1.5x native workload separation |
| Raw feedback difference is not itself replay invalidity | **Closed** | **N2b natural safe-side witness** + theory quotient |
| Criterion transfers across substrate/authorship | **Closed enough for PerCom** | Mosquitto, HA middleware, official HA blueprint, independently authored Better Thermostat |

No headline empirical cell remains open.

## 8. Empirical stop rule — now active

**Stop adding generic empirical systems.** Do not run N3 merely to increase controller count.

A new experiment is justified before submission only if paper drafting or adversarial review reveals a specific claim that cannot be defended by the sealed evidence and cannot be narrowed honestly. In particular, do not add a natural stochastic-overlap controller, physical thermostat/PID/TRV execution, radio/Matter/Zigbee experiment, or prevalence study just for breadth.

The highest-value work is now paper engineering:

1. freeze the three-contribution story and nine-page architecture;
2. separate exact structural invariants from timing statistics;
3. compress E3b/E3c/N1/N2/N2b into prediction-driven figures/tables rather than an experiment chronology;
4. sharpen related-work distinctions without claiming feedback-aware replay, support inclusion, or TV contraction as novel;
5. make PerCom relevance explicit through reactive pervasive middleware/smart-environment benchmarking;
6. draft under double-blind constraints;
7. run a three-reviewer adversarial red team before submission.

This stop rule is scientific discipline, not a claim of universality.