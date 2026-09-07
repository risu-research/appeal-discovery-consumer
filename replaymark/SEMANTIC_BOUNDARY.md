# ReplayMark semantic boundary — compiler-ready freeze

**Status:** boundary strengthened for bounded `q_{C,H}` compilation.  
**Original seed authority:** `replaymark-compiler-contract-seed@6da24cce48d1c2f6fe4bfabf4e01047e79b7e6eb`.  
**Scientific ancestry:** the exact `q_{C,H}` research gate remains the frozen prior authority; this package does not reinterpret its outcomes.  
**Current scope:** public semantic types, two-phase target semantics, bounded deterministic `q_{C,H}` compiler, and an implementation-independent definition oracle.  
**Still out of scope:** support masks, evidence-conditioned adjudication, `CompiledContract` realization, runtime gate insertion, replay/regeneration policy integration, BDD/bitset optimization, and new live experiments.

## 1. Public boundary stays deliberately small

The package root exports exactly six semantic types:

1. `ClaimSpec`
2. `TargetModel`
3. `EvidenceSpec`
4. `ProjectedAction`
5. `CompiledContract`
6. `Verdict`

Compiler stages, storage backends, runtime gates, substrate adapters, and verification oracles are explicit submodules rather than public semantic types.

The Replay-Sufficiency Factorization remains the dependency direction:

`claim -> projected actions -> q_{C,H} -> evidence image -> support envelope -> maximal certified reuse`.

This branch implements only the first bounded predictive-state arrow.

## 2. Claim and action boundaries

### `ClaimSpec`

The claim is normative. It declares stable identity, exact consequential action dimensions, a non-negative claim-bound consequence horizon, and the consequence endpoint. The target cannot silently refine or weaken it. Projection onto a dimension that an adapter did not establish fails closed.

### `ProjectedAction`

Actions are immutable canonical tuples of named scalar dimensions. ReplayMark core has no Home Assistant, MQTT, or thermostat vocabulary. Current adapters may supply coordinates such as `operation`, `target_class`, `variant`, and `delay_ms`; later adapters may add `target_identity` without changing core semantics.

Missing coordinates are not guessed. This is especially important for exact-target claims: the legacy AgentMark adapter knows a target *class* but does not invent exact resolved target identity.

## 3. Corrected `TargetModel`: decision state is a two-phase semantic object

The first seed exposed `distribution(state, feedback)`. That interface was sufficient for the old local support checker but was too ambiguous for the already-frozen `q_{C,H}` definition: E3b treats current feedback as part of the current decision condition, whereas the thermostat's feedback variables already live in its decision state.

The corrected protocol therefore represents one prediction step explicitly:

```text
decision_state
    -- current_distribution --> (current action, post-decision state)
post-decision state
    -- advance_distribution(future continuation) --> next decision_state
```

The split prevents a future continuation from being accidentally consumed as part of the current output.

A `TargetModel` now exposes:

- `decision_states` — the finite histories/conditions immediately before the current decision;
- `continuation_alphabet` — the claim-admitted future environmental/input events;
- `current_distribution(decision_state)` — exact mass over `(full action, post_state)`;
- `advance_distribution(post_state, continuation)` — exact mass over next decision states.

`EvidenceSpec` correspondingly denotes compatible **decision states/histories**, i.e. the executable finite form of `Omega(e)`.

This is a semantic correction to the software boundary, not a change to the paper's theory. It is the direct executable form of the definition used by the frozen E3b and Better-Thermostat q gate.

## 4. Legacy compatibility remains read-only

`replaymark.compat_agentmark` does not edit or rename the historical `agentmark` package.

The v2 lift maps each supported legacy condition `(controller_state, current_feedback)` into one canonical ReplayMark decision-state ID. `current_distribution` executes that already-conditioned legacy transition, and `advance_distribution` pairs the resulting post-controller state with the next admitted feedback symbol.

Action coordinates map as before:

| Frozen AgentMark object | ReplayMark meaning |
|---|---|
| `EventKey.operation` | `ProjectedAction['operation']` |
| `EventKey.target_class` | `ProjectedAction['target_class']` |
| `EventKey.variant` | `ProjectedAction['variant']` |
| `EventKey.delay_ms` | `ProjectedAction['delay_ms']` |
| `EventKey.next_state` | post-decision model state, never a claim coordinate |

The adapter fingerprint commits to the v2 lift schema plus the canonical legacy kernel specification.

## 5. Hard novelty/correctness wall: old quotient != `q_{C,H}`

`agentmark.minimize.quotient()` remains **algorithmic precedent only**. It computes a stable full-behavior quotient. It is never renamed, wrapped, or reported as ReplayMark's bounded claim-predictive state.

The new compiler must instead:

1. apply exactly the declared `ClaimSpec` projection;
2. define `q_{C,0}` only by the current projected output;
3. refine future distinctions through the model's admitted continuation structure;
4. compute exactly layers `0..H`;
5. perform no hidden `H+1` lookahead merely to claim convergence.

A fixed point is reported only if equality of adjacent **already-computed** partition relations is observed inside the requested horizon.

## 6. Deterministic theorem boundary is enforced in code

`TargetModel` can represent exact rational stochastic laws, but bounded compiler v1 intentionally accepts only deterministic point masses.

This is not an implementation shortcut. Ordinary partition refinement by distributions over quotient blocks can silently become a probabilistic-bisimulation construction, which is not automatically the same object as finite-horizon projected output-trace equivalence.

Therefore compiler v1 accepts exact deterministic current decisions and continuations, rejects multiple positive branches, rejects negative/missing/non-unit probability mass, and never approximates a stochastic target as deterministic.

The independent definition oracle *does* support finite stochastic models by enumerating exact projected trace laws. A future stochastic compiler must be separately proved against that definition before it can replace this fail-closed boundary.

## 7. Verification independence wall

Three layers remain deliberately separate:

- **production compiler:** `replaymark/q_compiler.py`, bounded partition refinement;
- **definition oracle:** `replaymark_oracle/definition_q_oracle.py`, direct continuation-word and output-trace-law enumeration;
- **historical/live scientific oracles:** existing theory validators and Home Assistant runtime validators.

The definition oracle does not import `replaymark.q_compiler`. Production code does not import the oracle or verification models.

This lets us test semantic agreement without proving an implementation with itself.

## 8. Current admitted verification

`replaymark_verification/verify_bounded_q.py` is required to close all of these gates:

- actual legacy E3b `ReactiveKernel` lift: exact q counts `[3,3,3,3]`;
- frozen 32-state thermostat: `[5,14,16,16,16]`;
- seven-preset 56-state robustness: `[5,14,16,16]` through H=3;
- exact historical depth-1 and depth-2 distinguishing words from the independent definition oracle;
- operation-vs-action projection separation;
- fail-closed stochastic-current and stochastic-continuation cases;
- exact-H no-lookahead discipline;
- exhaustive differential agreement on **all 5,832** complete deterministic 3-state / 2-continuation / 2-output machines through H=3, for **23,328** compiler-vs-definition partition relations;
- continuation-order invariance of the resulting equivalence relation.

Passing these tests establishes implementation fidelity for this compiler stage. It does not establish the later evidence/support/reuse contract.

## 9. Next boundary, deliberately not crossed here

Only after bounded q compilation is frozen may the next branch implement:

`EvidenceSpec -> S^- / S^+ -> VALID / INVALID / UNRESOLVED -> maximal reuse guard`.

No runtime E3b intervention is admitted before that evidence/support layer has its own independent oracle.
