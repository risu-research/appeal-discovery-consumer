# ReplayMark compiler contract seed — semantic boundary freeze

**Status:** first atomic compiler step only.  
**Base authority:** `replaymark-bt-mqtt-e2e-capstone@a1305f11807740fef1ac4ffe039385dcdaadc14d`.  
**Scope:** freeze the new `replaymark/` package boundary and the legacy compatibility map.  
**Not in scope:** `q_{C,H}` compilation, support-mask generation, runtime gate insertion, BDD/bitset optimization, E3b intervention, or any reinterpretation of frozen experiments.

## 1. Public boundary

The package root exports exactly six semantic types:

1. `ClaimSpec`
2. `TargetModel`
3. `EvidenceSpec`
4. `ProjectedAction`
5. `CompiledContract`
6. `Verdict`

This is deliberate. The compiler implementation, storage backend, runtime gate, and substrate adapters are not allowed to leak into the semantic API.

The dependency direction is the Replay-Sufficiency Factorization:

`ClaimSpec + TargetModel + EvidenceSpec -> future CompiledContract -> Verdict`

The future compiler will implement the stronger typed chain:

`claim -> projected actions -> q_{C,H} -> evidence image -> support envelope -> maximal certified reuse`.

## 2. Boundary decisions

### ClaimSpec

`ClaimSpec` is normative. It declares:

- stable claim identity;
- exact consequential action dimensions;
- a non-negative, claim-bound consequence horizon; and
- the consequence endpoint.

The target model cannot silently refine or weaken the claim. Projection onto a dimension the adapter did not establish raises `KeyError` rather than guessing.

### ProjectedAction

Actions are immutable tuples of named canonical scalar dimensions. The core has no Home Assistant, MQTT, or thermostat vocabulary.

This permits current coordinates such as:

- `operation`;
- `target_class`;
- `variant`;
- `delay_ms`;

and later adapters may add coordinates such as `target_identity` without changing ReplayMark core semantics. The legacy AgentMark adapter cannot establish exact target identity and therefore does not invent it; a claim requiring that coordinate will fail closed until a stronger adapter supplies it.

Dimension order is canonicalized, duplicates are rejected, floats and opaque Python objects are rejected, and missing claim-required dimensions fail closed.

### TargetModel

`TargetModel` is a protocol, not a concrete storage class. It exposes exact probability mass over:

`(full adapter-supplied action coordinates, successor target state)`.

This keeps the target semantics claim-independent. The future compiler, not the adapter, applies `ClaimSpec`.

The protocol intentionally permits a future explicit-model backend, validated live adapter, symbolic backend, or learned-model provider while keeping the compiler contract fixed. Learned-model uncertainty is not admitted by this seed and would require a separate epistemic contract.

### EvidenceSpec

The first compiler boundary represents retained target evidence extensionally:

`observation token -> compatible target states/histories`.

This is the finite executable form of `Omega(e)`. Observation sets may overlap. Unknown observations have no invented meaning and fail closed.

### CompiledContract

`CompiledContract` is also a protocol. It freezes observable semantics without prematurely freezing the representation.

A conforming future compiler artifact must expose:

- claim and provenance fingerprints;
- three-valued adjudication;
- the observations under which a historical action is reusable;
- a shortest separating witness when one exists; and
- canonical bytes for sealing.

A bitset backend and a BDD backend must therefore be observationally equivalent.

### Verdict

Only:

- `VALID`
- `INVALID`
- `UNRESOLVED`

are admitted.

No binary fallback is hidden inside the type boundary.

## 3. Exact legacy compatibility map

`replaymark.compat_agentmark` is a **read-only bridge**. It does not rename, edit, or import code into the historical `agentmark` package.

| Frozen AgentMark object | ReplayMark seed meaning |
|---|---|
| `ReactiveKernel` | `TargetModel` through read-only adapter |
| `EventKey.operation` | action dimension `operation` |
| `EventKey.target_class` | action dimension `target_class` |
| `EventKey.variant` | action dimension `variant` |
| `EventKey.delay_ms` | action dimension `delay_ms` |
| `EventKey.next_state` | target-model successor, **not** an action coordinate |
| projection `operation` | claim dimensions `operation` |
| projection `action` | `operation,target_class,variant` |
| projection `semantic` | `operation,target_class,delay_ms` |
| legacy full signature | structural precedent only; successor remains a target-model edge, not a claim projection |

The adapter fingerprint commits to both the adapter schema and canonical legacy kernel spec. It discards zero-mass atoms and requires the adapted supported distribution to sum exactly to one.

## 4. Hard novelty/correctness boundary

The existing `agentmark.minimize.quotient()` is **not** renamed to `q_{C,H}`.

It is algorithmic precedent for partition refinement, but it computes a stable full-behavior quotient. ReplayMark's future compiler must instead:

1. apply the declared `ClaimSpec` projection;
2. refine only distinctions needed for that claim;
3. consume successor structure through `TargetModel`;
4. stop at exactly the declared consequence horizon `H`.

This boundary prevents an implementation shortcut from invalidating ReplayMark's minimum-information claim.

Likewise, existing point-support logic is precedent only. The future compiler must generalize from one known target feedback value to `EvidenceSpec`'s compatible-world set and produce exact `VALID / INVALID / UNRESOLVED`.

## 5. Independence wall

These remain external scientific oracles and must not be imported by the future compiler:

- `agentmark_theory/verify_theory.py`
- `agentmark_natural_controllers/better_thermostat/n2_horizon_validate.py`

Production/compiler code may be compared against them, but may not share their adjudication implementation.

## 6. Seed verification

Run from repository root:

```bash
python replaymark/verify_seed.py
```

The checker uses the actual frozen AgentMark `ReactiveKernel` and verifies:

- structural `TargetModel` conformance;
- exact probability conservation;
- operation-level equivalence with action-level separation;
- fail-closed refusal to invent exact target identity absent from the legacy adapter;
- canonical action equality independent of mapping order;
- stable claim/evidence fingerprints;
- evidence normalization;
- fail-closed unknown evidence;
- refusal to reinterpret the legacy `full` structural signature as a claim projection; and
- the explicit rule that the old quotient is not `q_{C,H}`.

Passing this checker does **not** claim that the ReplayMark compiler exists. It proves only that the semantic boundary and compatibility seed are internally coherent.

## 7. Next admitted step

Only after this boundary is frozen should the next branch implement:

`TargetModel + ClaimSpec -> bounded claim-relative q_{C,H}`

with an independent brute-force definition oracle before any E3b runtime gate is inserted.
