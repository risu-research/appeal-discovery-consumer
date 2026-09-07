# ReplayMark semantic boundary — `CompiledContract` API re-freeze

**Status:** the finite deterministic semantic chain is implemented and independently
gated through bounded `q_{C,H}`, compiler-owned evidence semantics, evidence image,
support envelope, three-valued adjudication, maximal certified reuse `R*`,
production shortest predictive witnesses, and compiler-observed target semantic
provenance. This branch re-freezes the runtime-facing semantic API around those
established products; it does **not** implement the concrete contract backend.  
**Target-provenance authority:** `replaymark-target-provenance@b63254ea0e57b01f2bdf7f4ed95d2590ab04f721`.  
**Current branch scope:** correct the provisional `CompiledContract` Protocol so it
exposes auditable certificates, compiler-owned evidence uncertainty,
compiler-observed target provenance, distinct predictive/reuse explanations, and
R* without adding execution policy.  
**Still out of scope:** concrete contract packaging, runtime raw-observation
canonicalization, concrete historical-action realization validation, target-native
fallback policy, evidence-acquisition policy, runtime E3b intervention, stochastic
q compilation, BDD/bitset optimization, and new live experiments.

## 1. Executable semantic chain

The established production chain is:

`TargetModel -> ObservedTargetSemantics -> ClaimSpec -> q_{C,H}`

then:

`CompiledEvidenceSemantics -> q[Omega(e)] -> S-/S+ -> VALID/INVALID/UNRESOLVED -> R*`.

Predictive continuation witnesses are explanation products of q and remain
semantically separate from R* counterexample worlds.

## 2. Target provenance

`TargetModel.fingerprint` is provider metadata, not semantic authority.
ReplayMark observes and seals the complete finite two-phase target semantics
before q compilation and computes a compiler-derived `target_semantic_digest`.
The q compiler consumes that immutable snapshot rather than re-querying the
provider, closing the semantic-hash/TOCTOU gap.

The semantic digest is claim-independent and covers full positive-probability
action/transition laws. Snapshot identity separately retains provider metadata
and declared continuation order.

## 3. Bounded claim-predictive state

For deterministic input-enabled targets:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for each admitted u)`.

Only layers `0..H` are compiled. No hidden `H+1` lookahead is used.
The independent q oracle enumerates continuation words and projected trace laws.

## 4. Evidence semantics

Production authoring supplies a forward observation-support relation:

`O(w) = set of retained-evidence tokens possible in modeled world w`.

ReplayMark, not the adapter author, derives:

`Omega(e) = { w : e in O(w) }`.

The compiler guarantees exact inversion relative to the modeled finite target.
The external adapter obligation remains conservative semantic adequacy:

`Omega_real(e) subseteq Omega_model(e)`.

Over-approximation may reduce reuse; under-approximation can create false
certification and is not admitted.

## 5. Evidence image, support envelope, and adjudication

For evidence token `e`:

`I_{C,h}(e) = q_{C,h}[Omega(e)]`.

Then:

`S_C^-(e) = intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) = union_{w in Omega(e)} S_C(w)`.

For recorded claim-projected action `z`:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` otherwise.

UNRESOLVED is exact semantic underdetermination, not a confidence score.

## 6. Maximal certified reuse R*

For fixed evidence and support validity:

`R*(e,z) = REUSE iff z in S_C^-(e)`.

Thus VALID maps to REUSE and both INVALID/UNRESOLVED map to DO_NOT_REUSE.
`DO_NOT_REUSE` is not a regeneration/fallback command. R* is pointwise maximal
among fixed-evidence binary support-sound reuse rules.

## 7. Witness semantics remain split

ReplayMark has two constructive explanations and the API must not conflate them.

A **predictive continuation witness** is defined for two target worlds and is the
shortest admitted continuation whose claim-projected traces differ. It explains q
inequivalence and depends on neither evidence nor historical action.

An **R* counterexample world** is defined for one `(e,z)` pair and is a raw world
in `Omega(e)` that excludes `z` from positive projected support. It explains why
additional reuse would be support-unsound. It is not a continuation sequence and
has no shortest-word semantics.

## 8. Re-frozen `CompiledContract` principles

The public contract freezes **semantic behavior, certificates, and provenance**,
not storage layout.

Inputs called `observation_token` are already-canonical retained-evidence tokens.
Raw runtime event/sensor canonicalization remains outside the contract.

The contract returns rich semantic certificates instead of lossy summaries:

- `adjudicate(...) -> Adjudication`, not bare `Verdict`;
- `certify_reuse(...) -> RStarDecision`, preserving the original three-valued
  verdict; and
- `predictive_witness(...) -> PredictiveContinuationWitness | None`.

No contract operation executes a historical action or chooses regenerate/refine/
abort/fallback policy.

## 9. Re-frozen provenance surface

A conforming contract exposes:

- `claim` and `claim_fingerprint`;
- `target_provider_fingerprint` as provider metadata;
- `target_semantic_digest` as compiler-observed target semantic authority;
- `target_snapshot_fingerprint` as target snapshot artifact identity;
- `evidence_semantics_fingerprint` and compiler-derived
  `evidence_relation_fingerprint`;
- `quotient_fingerprint`;
- `support_envelope_fingerprint`; and
- `predictive_witness_index_fingerprint`.

These bindings let an external reviewer check that returned adjudication/reuse/
witness certificates belong to the exact compiled semantic artifacts.

## 10. Re-frozen normative operations

The semantic operations are exactly:

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

`canonical_bytes()` and `fingerprint()` provide concrete contract artifact
identity.

The public predictive-witness operation is deliberately fixed at the
claim-declared horizon H. Lower-depth q diagnostics remain compiler-level tools,
not runtime contract semantics.

## 11. Cross-operation invariants for any concrete backend

A future concrete implementation must preserve:

1. `claim_fingerprint == claim.fingerprint()`.
2. `compatible_worlds(e)` equals the compiler-derived `Omega(e)` and never invents
   fallback semantics for an unknown token.
3. `adjudicate(e,z)` is bound to this claim/evidence/support artifact and applies
   the exact claim projection.
4. `certify_reuse(e,z)` preserves that adjudication verdict and returns REUSE iff
   the verdict is VALID.
5. `reuse_counterexample_world(e,z)` is `None` iff reuse is certified; otherwise
   it returns a compatible raw target world excluding the projected z.
6. `predictive_witness(w1,w2)` is evidence/action independent, bound to this
   claim/quotient, and shortest at H.
7. `predictive_witness(w1,w2)` is `None` iff the pair is q-equivalent at H.
8. Unknown worlds/tokens fail closed.
9. No normative method executes, regenerates, retries, refines evidence, aborts,
   or selects fallback policy.

## 12. Deliberately removed provisional API

The old seed members are no longer normative:

- `target_model_fingerprint` — ambiguous; split into provider metadata versus
  compiler-observed semantic authority;
- `evidence_fingerprint` — ambiguous; split into evidence artifact/relation
  identities;
- `adjudicate(...) -> Verdict` — replaced by full `Adjudication` certificate;
- `reusable_observations(...)` — convenience enumeration, not theorem primitive;
- `shortest_witness(observation, historical_action)` — conflated two distinct
  witness semantics.

This is an intentional correction of a provisional interface before concrete
packaging, not a compatibility-preserving deprecation.

## 13. Backend neutrality

A future explicit-table, Python-int bitset, Roaring, BDD, or other backend may
implement the Protocol. Backend indexes, caches, and batch helpers are
non-normative unless separately frozen.

Concrete artifact fingerprints may differ across intentionally different
serializations/backends. The semantic authorities and all observable certificate
behavior above must remain equivalent.

## 14. Verification independence and shared TCB

The project continues to use algorithmically independent definition oracles above
a shared semantic-contract TCB:

- q refinement versus literal continuation-word trace laws;
- predictive backpointers versus shortest-word enumeration;
- compiler-owned evidence inversion versus literal relation inversion;
- compiled support/adjudication/R* versus raw compatible-world support; and
- two-pass target semantic snapshotting versus independent provenance
  canonicalization.

The API re-freeze adds no new mathematical theorem. Its gate verifies that the
Protocol surface exactly matches those established semantic products and that the
provisional conflated/policy-bearing names cannot silently re-enter.

## 15. Remaining trust boundaries

This API does not prove:

- physical/runtime adequacy of the TargetModel;
- conservative adequacy of the observation adapter to reality;
- correctness of raw runtime observation tokenization;
- equivalence between a concrete historical action realization and the modeled
  target-side transition; or
- correctness of any fallback execution policy.

Those remain explicit subsequent boundaries.

## 16. Next boundary

If this API gate closes with all earlier semantic gates green, the next admissible
step is **concrete `CompiledContract` packaging only**: assemble the already-proved
artifacts behind this interface without changing observable semantics.

Runtime intervention, fallback behavior, and new experiments remain later steps.
