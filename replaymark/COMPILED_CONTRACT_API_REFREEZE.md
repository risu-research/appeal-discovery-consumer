# ReplayMark `CompiledContract` API re-freeze

## 1. Review result before re-freeze

A fresh review of the implemented semantic chain found no contradiction that
requires reopening bounded q, compiler-owned evidence inversion, support
envelopes, three-valued adjudication, R*, predictive witnesses, or
compiler-observed target provenance.

The remaining concrete problem was the **provisional seed API**. It predated most
of those results and had become semantically wrong in several ways:

- it exposed only a provider `target_model_fingerprint`, even though compiler-
  observed target semantic provenance is now the authority;
- it returned a bare `Verdict`, discarding the adjudication certificate;
- it exposed `reusable_observations`, which is a convenience enumeration rather
  than a theorem primitive and may be expensive/backend-specific;
- it conflated predictive q witnesses with reuse counterexamples through
  `shortest_witness(observation, historical_action)`; and
- it did not expose the R* certificate directly.

The correct next step is therefore an API **re-freeze**, not a concrete runtime
implementation.

## 2. Design rule: expose theorem products, not policy

The contract is an immutable semantic artifact. Its public operational surface
must answer only questions already justified by the compiled semantics.

It does **not**:

- canonicalize raw runtime sensor/events into evidence tokens;
- execute a historical action;
- choose target-native regeneration;
- request more evidence;
- abort a run;
- choose a retry/fallback strategy; or
- optimize execution cost.

`RStarDecision.disposition == REUSE` means only that historical projected-decision
reuse is certified by the fixed claim/evidence model. `DO_NOT_REUSE` is not a
regeneration command.

## 3. Design rule: return certificates, not lossy summaries

The old provisional `adjudicate(...) -> Verdict` throws away information that the
production adjudicator already proves and seals. The re-frozen API therefore
returns the full `Adjudication` certificate.

Likewise R* is surfaced as a full `RStarDecision`, preserving the underlying
three-valued verdict even though R* collapses INVALID and UNRESOLVED to
DO_NOT_REUSE.

This makes the public boundary auditable and prevents callers from reconstructing
semantic reasoning from partial booleans.

## 4. Design rule: distinguish the two witness semantics

The final contract has two separate explanation operations.

### 4.1 Predictive q witness

`predictive_witness(left_world, right_world)` returns a
`PredictiveContinuationWitness` or `None` at the contract's claim-declared
horizon H.

It answers:

> Why are these two target worlds predictively distinguishable for this claim?

It depends on neither evidence nor historical action.

The public contract intentionally does not expose a lower-depth parameter. A
compiled contract represents one normative claim and one normative H. Lower-layer
diagnostics remain available in compiler artifacts, but they are not part of the
runtime semantic contract.

### 4.2 R* counterexample world

`reuse_counterexample_world(observation_token, historical_action)` returns one
canonical raw compatible world excluding the claim-projected historical action,
or `None` iff R* certifies REUSE.

It answers:

> Which modeled target world proves that extra historical reuse here would be
> support-unsound?

It is not a continuation sequence and carries no shortestness claim.

The old generic `shortest_witness(observation, historical_action)` operation is
removed from the normative API.

## 5. Design rule: make epistemic uncertainty auditable

`compatible_worlds(observation_token)` exposes the compiler-derived
`Omega(e)` from `CompiledEvidenceSemantics`.

This is not required for the hot path, but it is valuable for artifact review and
for explaining why a verdict is unresolved. It also makes clear that the runtime
input is an already-canonical evidence **token**, not a raw sensor event.

Unknown evidence tokens fail closed; the contract must never invent a nearest or
default meaning.

## 6. Design rule: semantic provenance must be explicit

The public contract distinguishes provider metadata from compiler-observed
semantic identity.

Required target provenance properties are:

- `target_provider_fingerprint`: provider-supplied metadata;
- `target_semantic_digest`: compiler-observed modeled-target semantic authority;
- `target_snapshot_fingerprint`: artifact identity including provider/order
  metadata.

Evidence provenance is exposed as:

- `evidence_semantics_fingerprint`: the complete compiled evidence-semantics
  artifact identity; and
- `evidence_relation_fingerprint`: compiler-derived identity of the forward
  world-to-possible-observation relation.

The contract also exposes the exact `quotient_fingerprint`,
`support_envelope_fingerprint`, and `predictive_witness_index_fingerprint` so
returned certificates can be checked against the stages from which they were
compiled.

## 7. Re-frozen public operations

The normative semantic operations are now exactly:

```text
compatible_worlds(observation_token)
    -> tuple[target_world, ...]

adjudicate(observation_token, historical_action)
    -> Adjudication

certify_reuse(observation_token, historical_action)
    -> RStarDecision

reuse_counterexample_world(observation_token, historical_action)
    -> target_world | None

predictive_witness(left_world, right_world)
    -> PredictiveContinuationWitness | None
```

`canonical_bytes()` and `fingerprint()` provide artifact identity.

## 8. Required cross-operation invariants

Any concrete `CompiledContract` backend must satisfy all of the following.

1. `claim_fingerprint == claim.fingerprint()`.
2. Every compatible world returned by `compatible_worlds(e)` belongs to the
   target domain sealed into the contract.
3. `adjudicate(e,z)` returns a certificate bound to this claim, evidence
   semantics, q depth, and support envelope.
4. `certify_reuse(e,z)` preserves the exact adjudication verdict and returns
   REUSE iff that verdict is VALID.
5. `reuse_counterexample_world(e,z) is None` iff `certify_reuse(e,z)` is REUSE.
6. Otherwise the returned counterexample belongs to `Omega(e)` and does not
   positively support the claim projection of z.
7. `predictive_witness(w1,w2)` is independent of evidence and historical actions,
   is bound to this quotient/claim, and is shortest at the claim-declared H.
8. `predictive_witness(w1,w2) is None` iff the two worlds are q-equivalent at H.
9. Unknown observation tokens/worlds fail closed; no implicit fallback semantics
   are permitted.
10. No public operation executes, regenerates, retries, refines evidence, or
    selects a runtime fallback.

## 9. Backend neutrality

The API freezes observable semantics, not storage representation.

A future explicit-table, Python-int bitset, Roaring bitmap, BDD, or other backend
may implement the same contract. Backend-specific indexes, caches, and batch
operations are non-normative extensions unless separately frozen.

`fingerprint()` is the concrete contract artifact identity and may therefore
change if a different backend/compiler serialization is intentionally used. The
semantic authorities exposed above—claim fingerprint, compiler-observed target
semantic digest, evidence relation identity, and certificate behavior—must not
change merely because storage changes.

## 10. What was deliberately removed

The following provisional members are no longer normative:

- `target_model_fingerprint` — ambiguous; replaced by explicit provider versus
  compiler-observed provenance;
- `evidence_fingerprint` — ambiguous; replaced by evidence artifact/relation
  identities;
- `adjudicate(...) -> Verdict` — replaced by the full certificate;
- `reusable_observations(...)` — convenience enumeration, not semantic core;
- `shortest_witness(observation, historical_action)` — semantically conflated
  predictive and reuse explanations.

Removing these before concrete packaging is intentional API correction, not
backward-compatible deprecation: the prior interface was explicitly provisional.

## 11. Scope still not crossed

This re-freeze does not implement the concrete contract object and does not add:

- runtime raw-observation canonicalization;
- historical concrete-action realization validation;
- target-native fallback policy;
- evidence acquisition policy;
- live E3b intervention;
- stochastic q compilation; or
- BDD/bitset optimization.

The next step, if admitted after this API gate, is concrete packaging of the
already-proved semantic artifacts behind this re-frozen boundary without changing
observable semantics.
