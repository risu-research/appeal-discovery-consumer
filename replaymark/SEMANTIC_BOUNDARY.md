# ReplayMark semantic boundary — concrete `CompiledContract` packaging

**Status:** the finite deterministic semantic chain is implemented, independently
gated, API-frozen, and now concretely packaged into a self-contained immutable
`ExplicitCompiledContract`. The concrete object embeds the sealed target snapshot,
bounded `q_{C,H}`, compiler-owned evidence semantics, q evidence image, support
envelope, and shortest predictive-witness index, and implements the re-frozen
`CompiledContract` Protocol without adding execution policy.  
**API authority:** `replaymark-compiled-contract-api-refreeze@fc14d3160df7dfb83a7b7a01c438d0dbb081fb1d`.  
**Current branch scope:** package only the already-established semantic artifacts,
bind them transitively, provide provider-free runtime queries, and provide strict
canonical serialization/reload.  
**Still out of scope:** raw runtime observation canonicalization, concrete
historical-action realization validation, target-native fallback policy,
evidence-acquisition policy, live E3b intervention, stochastic q compilation,
BDD/bitset optimization, and new live experiments.

## 1. Established semantic chain

The production chain remains:

`TargetModel -> ObservedTargetSemantics -> ClaimSpec -> q_{C,H}`

then:

`ObservationSupportModel -> CompiledEvidenceSemantics -> Omega(e)`

then:

`q[Omega(e)] -> S-/S+ -> VALID/INVALID/UNRESOLVED -> R*`.

Predictive continuation witnesses remain explanation products of q and are
semantically separate from R* counterexample worlds.

Concrete packaging adds no new theorem to this chain.

## 2. Target provenance

`TargetModel.fingerprint` remains provider metadata, not semantic authority.

ReplayMark observes and seals the complete finite two-phase target semantics and
computes a compiler-derived `target_semantic_digest`. The bounded-q compiler binds
itself to that observed snapshot.

Concrete packaging additionally checks that the embedded q artifact's provider
metadata, semantic digest, snapshot fingerprint, domain digest, current-semantics
digest, and advance-semantics digest all equal the embedded
`ObservedTargetSemantics`.

The package then re-derives q's current projected actions, deterministic
successors, and every bounded partition from that snapshot.

## 3. Bounded claim-predictive state

For deterministic input-enabled targets:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for each admitted u)`.

Only layers `0..H` are admitted.

A concrete contract must package exactly the claim-declared H. A shallower
evidence image or predictive-witness index is an audit artifact, not a normative
runtime contract, and is rejected by packaging.

## 4. Evidence semantics

Production authoring supplies:

`O(w) = set of retained-evidence tokens possible in modeled world w`.

ReplayMark derives:

`Omega(e) = { w : e in O(w) }`.

Concrete packaging embeds the complete `CompiledEvidenceSemantics`, including the
forward relation and derived inverse `EvidenceSpec`.

`compatible_worlds(e)` reads only this sealed compiler-derived inverse.

Unknown evidence tokens fail closed.

## 5. Evidence image and support envelope

At the claim horizon H:

`I_{C,H}(e) = q_{C,H}[Omega(e)]`.

Then:

`S_C^-(e) = intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) = union_{w in Omega(e)} S_C(w)`.

Concrete packaging does not trust the existing support artifact solely by
fingerprint.

For every evidence token it re-evaluates positive projected support directly from
the sealed raw target snapshot and checks that the embedded `S^-` and `S^+`
equal the raw-world intersection and union.

This binds the support theorem transitively back to target semantics.

## 6. Three-valued adjudication

For recorded claim-projected action `z`:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` otherwise.

`adjudicate(e,z)` returns the full `Adjudication` certificate.

The concrete contract delegates this operation to the already-gated production
adjudicator over the sealed support envelope.

## 7. Maximal certified reuse R*

For fixed evidence and support validity:

`R*(e,z) = REUSE iff z in S_C^-(e)`.

Therefore:

- VALID -> REUSE;
- INVALID -> DO_NOT_REUSE;
- UNRESOLVED -> DO_NOT_REUSE.

`certify_reuse(e,z)` returns the full `RStarDecision` and preserves the original
three-valued verdict.

`DO_NOT_REUSE` remains a theorem result, not a regeneration command.

## 8. Witness semantics remain split

A **predictive continuation witness** is defined for two target worlds. It is the
shortest admitted continuation whose claim-projected traces differ.

An **R* counterexample world** is defined for one `(e,z)` pair. It is a raw
compatible target world excluding z from positive projected support.

They are not interchangeable.

The concrete contract exposes:

```text
predictive_witness(left_world, right_world)
reuse_counterexample_world(observation_token, historical_action)
```

as separate operations.

## 9. Concrete backend

The first concrete backend is:

`replaymark.compiled_contract.ExplicitCompiledContract`.

It embeds:

- `ObservedTargetSemantics`;
- `BoundedQuotient`;
- `CompiledEvidenceSemantics`;
- `QEvidenceImage`;
- `SupportEnvelope`; and
- `PredictiveWitnessIndex`.

It is frozen/immutable and contains no live `TargetModel` or
`ObservationSupportModel` reference.

## 10. Provider-free runtime

After compilation, every re-frozen semantic operation runs from embedded sealed
artifacts only:

```text
compatible_worlds(e)
adjudicate(e,z)
certify_reuse(e,z)
reuse_counterexample_world(e,z)
predictive_witness(w1,w2)
canonical_bytes()
fingerprint()
```

The original target/evidence providers may disappear, change, or become
unavailable without affecting an already-loaded contract.

This does not make the original model adequate to physical reality; it only
closes runtime dependence on the authoring providers.

## 11. End-to-end packaging stability

`compile_explicit_contract(...)` observes the target before the constituent
compiler stages and again after them.

The q artifact must identify exactly the pre-observed snapshot, and the final
observation must be byte-identical to that snapshot.

Any drift in modeled target semantics, domain, provider metadata, or declared
continuation order during packaging fails closed.

## 12. Re-frozen provenance surface

The concrete object implements the existing Protocol properties exactly:

- `claim`;
- `claim_fingerprint`;
- `target_provider_fingerprint`;
- `target_semantic_digest`;
- `target_snapshot_fingerprint`;
- `evidence_semantics_fingerprint`;
- `evidence_relation_fingerprint`;
- `quotient_fingerprint`;
- `support_envelope_fingerprint`; and
- `predictive_witness_index_fingerprint`.

No new package-root semantic type is introduced.

The root `replaymark.__all__` remains exactly the six previously frozen boundary
types.

## 13. Canonical concrete artifact

`canonical_bytes()` contains the complete semantic package, not merely references
or hashes.

The record has:

```text
schema
compiler_id
manifest
artifacts:
  target_snapshot
  bounded_quotient
  evidence_semantics
  evidence_image
  support_envelope
  predictive_witness_index
```

The manifest is an audit index only. The loader recomputes it from the embedded
artifacts.

`fingerprint()` is SHA-256 over the exact canonical byte string.

## 14. Strict reload semantics

`load_compiled_contract(bytes)` performs strict reconstruction.

It rejects:

- malformed/non-UTF-8 JSON;
- duplicate JSON object keys;
- non-finite numeric constants;
- missing or unknown fields;
- foreign schemas/compiler identifiers;
- malformed exact rational masses;
- forged manifests;
- target semantic digest mismatches;
- q/snapshot mismatches;
- evidence/q mismatches;
- support artifacts that are not exactly derivable from embedded inputs;
- witness indexes that are not exactly derivable from q;
- artifacts compiled below the normative H; and
- non-canonical JSON byte encodings.

Successful loading therefore re-validates both semantic binding and canonical
artifact identity.

## 15. Concrete cross-operation invariants

The concrete backend enforces the API re-freeze invariants:

1. `claim_fingerprint == claim.fingerprint()`.
2. `compatible_worlds(e)` equals compiler-derived `Omega(e)`.
3. `adjudicate(e,z)` is bound to the embedded support envelope and claim.
4. `certify_reuse(e,z)` preserves that adjudication and returns REUSE iff VALID.
5. `reuse_counterexample_world(e,z)` is `None` iff reuse is certified.
6. Otherwise the counterexample belongs to `Omega(e)` and excludes projected z.
7. `predictive_witness(w1,w2)` is bound to the embedded q/claim at H.
8. It is `None` iff the pair is q-equivalent at H.
9. Unknown worlds/tokens fail closed.
10. No method executes, regenerates, retries, refines evidence, aborts, or chooses
    fallback.

## 16. Backend neutrality

`ExplicitCompiledContract` is the first reference backend, not a theorem-level
storage requirement.

A future bitset, Roaring, BDD, or other backend may implement the same
`CompiledContract` Protocol.

Such a backend may use a different concrete artifact serialization and therefore
have a different artifact fingerprint. It must preserve the frozen semantic
authority and observable certificate behavior.

## 17. Verification independence

The earlier semantic gates remain unchanged:

- q refinement vs literal continuation-word oracle;
- predictive backpointers vs shortest-word enumeration;
- evidence inversion vs literal inverse relation;
- support/adjudication/R* vs raw-world definition oracles;
- target snapshotting vs independent provenance canonicalization.

Concrete packaging adds assembly-specific verification rather than replacing
those gates.

It checks:

- Better Thermostat `5 -> 14 -> 16` preservation;
- known VALID/INVALID/UNRESOLVED/R* cells;
- one-step N2b predictive witness;
- provider-free runtime after the source TargetModel is made unusable;
- canonical serialize/load round trips;
- manifest/support/schema/canonicality tamper rejection;
- exact-H enforcement; and
- complete packaging of all 64 labeled deterministic 2-state/2-input/2-output
  machines, with every evidence/action R* pair compared to the raw oracle.

The existing 5,832-machine semantic gates are still rerun in CI.

## 18. Remaining trust boundaries

Concrete packaging still does not prove:

- physical/runtime adequacy of the TargetModel;
- conservative adequacy of the observation adapter to reality;
- raw event -> canonical observation-token correctness;
- concrete historical API action -> `ProjectedAction` realization correctness;
- fallback execution correctness;
- evidence-acquisition policy correctness;
- stochastic production q semantics; or
- live-system intervention correctness.

These boundaries are not hidden inside the concrete contract.

## 19. Next boundary

With the concrete package closed, the semantic compiler is artifact-complete for
the established finite deterministic scope.

The next admissible boundary is runtime realization, not another semantic theorem:

```text
raw retained observation
    -> canonical evidence token

historical concrete action
    -> verified ProjectedAction realization

CompiledContract
    -> semantic certificate

separate execution policy
    -> reuse / target-native fallback / abort / evidence refinement
```

Observation parsing, historical-action identity, and execution policy must remain
separate from the proved semantic contract.
