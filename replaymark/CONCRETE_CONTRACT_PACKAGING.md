# ReplayMark concrete `CompiledContract` packaging freeze

## 1. Status

This stage implements the first concrete backend of the re-frozen
`CompiledContract` semantic API without changing the established semantics.

Authority entering this stage:

`replaymark-compiled-contract-api-refreeze@fc14d3160df7dfb83a7b7a01c438d0dbb081fb1d`

Concrete backend:

`replaymark.compiled_contract.ExplicitCompiledContract`

Concrete schema:

`replaymark.compiled-contract.explicit.v1`

Packager/compiler identifier:

`replaymark.reference-packager.explicit.v1`

The package root remains unchanged: only the six semantic boundary types
`ClaimSpec`, `TargetModel`, `EvidenceSpec`, `ProjectedAction`,
`CompiledContract`, and `Verdict` are exported from `replaymark`.

## 2. What concrete packaging means

The contract is a self-contained immutable semantic artifact containing:

1. the compiler-observed target semantic snapshot;
2. the exact bounded claim-relative quotient `q_{C,H}`;
3. compiler-derived evidence semantics and `Omega(e)`;
4. the q image of every evidence token at the claim-declared horizon;
5. the deterministic support envelope `S^- / S^+`; and
6. the complete shortest predictive-witness index at H.

The original `TargetModel` and `ObservationSupportModel` are not retained.
After compilation, runtime/audit operations consume only the sealed artifacts.

This is deliberately stronger than an object holding references to live adapters:
a loaded contract can adjudicate, certify reuse, expose counterexamples, and
explain predictive distinctions even if the source provider no longer exists.

## 3. No new theorem

Concrete packaging adds no new replay-validity rule.

The normative semantics remain exactly:

`Omega(e) = {w : e in O(w)}`

`S^-(e) = intersection_{w in Omega(e)} S(w)`

`S^+(e) = union_{w in Omega(e)} S(w)`

and:

- `VALID` iff `z in S^-(e)`;
- `INVALID` iff `z notin S^+(e)`;
- `UNRESOLVED` otherwise;
- `R*(e,z) = REUSE` iff the verdict is `VALID`.

Predictive continuation witnesses remain separate from R* counterexample worlds.

## 4. Offline compilation path

`compile_explicit_contract(...)` orchestrates only already-gated stages:

```text
TargetModel
  -> observe_target_semantics
  -> compile_bounded_q
ObservationSupportModel
  -> compile_evidence_semantics
q + evidence
  -> compile_evidence_image at H
  -> compile_support_envelope
q
  -> compile_predictive_witnesses at H
all sealed artifacts
  -> package_compiled_contract
```

The orchestration layer does not implement any of those semantic transformations
itself.

## 5. End-to-end target stability gate

Packaging observes the target before the constituent compiler stages and again
after them.

In addition, the q artifact must identify exactly the pre-observed target snapshot.

Compilation therefore fails closed if target semantics, target domain, provider
metadata, or declared continuation order drift across the end-to-end packaging
window.

This is stricter than merely trusting the provider fingerprint and preserves the
compiler-observed semantic-provenance rule established earlier.

## 6. Assembly-time binding validation

`ExplicitCompiledContract` does not accept a collection of artifacts merely
because their fingerprint strings look compatible.

Before construction succeeds it checks, at minimum:

- target snapshot schema and internal content-derived digests;
- q schema, target provenance, claim identity, state domain, continuation order,
  current action table, successor table, and exactly H+1 layers;
- independent re-derivation of every q partition from the sealed target snapshot;
- exact evidence target domain and compiler-derived inverse relation;
- evidence image identity, relation identity, token set, raw compatible worlds,
  q blocks, and exact claim horizon H;
- exact re-computation of the evidence image from q + compiled evidence;
- exact support-envelope binding and re-computation;
- raw-world re-derivation of `S^-` as support intersection and `S^+` as support
  union for every evidence token;
- predictive-witness claim/q/domain/continuation/H bindings;
- exact re-computation of the production shortest predictive-witness index; and
- canonical SHA-256 identities for every embedded component.

This makes the concrete package a transitive binding of the entire semantic chain,
not a manifest of unverified hashes.

## 7. Provider-free runtime behavior

The concrete contract implements exactly the re-frozen semantic surface:

```text
compatible_worlds(e)
adjudicate(e,z)
certify_reuse(e,z)
reuse_counterexample_world(e,z)
predictive_witness(w1,w2)
canonical_bytes()
fingerprint()
```

None of these operations queries the source `TargetModel` or
`ObservationSupportModel`.

The production R* counterexample operation is computed directly from the sealed
target snapshot: for a non-reusable `(e,z)`, it returns the first canonical world
in `Omega(e)` whose positive claim-projected current support excludes `z`.

For a reusable pair it returns `None`.

## 8. Deterministic counterexample semantics

`reuse_counterexample_world(e,z)` does not claim shortestness.

Its canonicality rule is simply the existing canonical order of
`EvidenceSpec.compatible_states(e)`.

Therefore:

- REUSE -> `None`;
- DO_NOT_REUSE -> one deterministic raw-world counterexample;
- the returned world is always in `Omega(e)`; and
- the returned world excludes the projected historical action from positive
  support.

This is constructive evidence for pointwise maximality, not a fallback policy.

## 9. Predictive witness semantics

`predictive_witness(w1,w2)` delegates to the sealed
`PredictiveWitnessIndex` at exactly the claim-declared H.

It returns:

- `None` iff the worlds are q-equivalent at H;
- otherwise the canonical shortest admitted continuation whose projected traces
  differ.

It never receives an evidence token or historical action.

## 10. Self-contained canonical artifact

`canonical_bytes()` serializes the complete contract, not only component hashes.

The canonical record contains:

```text
schema
compiler_id
manifest:
  claim_fingerprint
  target_provider_fingerprint
  target_semantic_digest
  target_snapshot_fingerprint
  evidence_semantics_fingerprint
  evidence_relation_fingerprint
  quotient_fingerprint
  support_envelope_fingerprint
  predictive_witness_index_fingerprint
artifacts:
  target_snapshot
  bounded_quotient
  evidence_semantics
  evidence_image
  support_envelope
  predictive_witness_index
```

The manifest is redundant by design: it is an audit index. It is never trusted
over the embedded artifacts.

The contract fingerprint is SHA-256 over the exact canonical bytes.

## 11. Strict canonical loader

`load_compiled_contract(bytes)` reconstructs a concrete contract from its canonical
JSON artifact.

The loader fails closed on:

- non-UTF-8 bytes;
- malformed JSON;
- duplicate JSON object keys;
- `NaN`, `Infinity`, or other non-finite JSON constants;
- missing fields;
- unknown fields;
- foreign schemas or compiler identifiers;
- malformed exact rational masses;
- malformed action coordinates;
- forged target semantic digests;
- forged component fingerprints;
- cross-artifact mismatches;
- a support envelope not equal to the one derivable from the embedded inputs;
- a predictive witness index not equal to the one derivable from q;
- an evidence image or witness index compiled below H; and
- any JSON byte representation that is not exactly ReplayMark's canonical
  serialization.

A successful load therefore performs semantic binding validation and canonicality
validation together.

## 12. Why non-canonical JSON is rejected

Semantically equivalent pretty-printed JSON is intentionally not accepted by the
strict loader.

The contract fingerprint is an artifact identity over bytes. Permitting multiple
byte encodings for one admitted artifact would create avoidable ambiguity between
"same semantic record" and "same certified artifact".

Tools that want a human-readable rendering may decode the JSON for display, but
the certified portable object is the canonical byte string.

## 13. Backend neutrality is preserved

`ExplicitCompiledContract` is the first reference backend, not a permanent storage
mandate.

Future bitset, Roaring, BDD, or other implementations may satisfy the same
`CompiledContract` Protocol.

They must preserve the re-frozen observable semantic behavior and provenance
bindings. A different concrete backend may have a different artifact fingerprint
if it intentionally uses a different serialization.

No backend-specific helper is added to the package-root semantic API.

## 14. Verification strategy

The concrete packaging gate includes four distinct layers.

### 14.1 Frozen Better Thermostat witness

The 32-state thermostat model must preserve:

`5 -> 14 -> 16`

for q depths 0, 1, and 2.

The packaged contract must also realize:

- N2b retained `SET_AWAY`: VALID / REUSE;
- mixed `SET_HOME`: UNRESOLVED / DO_NOT_REUSE;
- mixed `SET_AWAY`: INVALID / DO_NOT_REUSE;
- strong `SET_HOME`: VALID / REUSE; and
- the expected one-step predictive witness separating the N2b pair.

### 14.2 Provider-free runtime test

A source TargetModel is changed after compilation so every provider access raises.

All contract operations, canonical serialization, and canonical reload must still
succeed.

This proves that the concrete artifact does not silently depend on live provider
calls.

### 14.3 Tamper/fail-closed tests

The gate verifies rejection of:

- forged manifest identities;
- forged support artifacts;
- non-canonical JSON;
- duplicate JSON keys;
- unknown fields;
- foreign concrete schemas;
- unknown runtime evidence tokens;
- unknown predictive worlds;
- shallower-than-H evidence images; and
- shallower-than-H predictive witness indexes.

The concrete object itself must be immutable and expose no execute/regenerate/
fallback/retry/abort/evidence-refinement policy surface.

### 14.4 Complete two-state packaging enumeration

Every complete labeled deterministic machine with:

- 2 states;
- 2 output labels; and
- 2 continuation symbols

is packaged.

There are 64 such machines.

For every non-empty evidence subset and both recorded output actions, the concrete
contract's R* result is compared with the raw-world definition oracle. Every
contract is also canonical-serialized and strict-loaded, and predictive-witness
presence is checked against final q equivalence.

This is packaging-specific exhaustive coverage on top of the already-frozen
5,832-machine semantic gates.

## 15. CI closure rule

The concrete packaging branch is admitted only when:

1. the semantic seed gate passes;
2. the re-frozen CompiledContract API gate passes;
3. the new concrete packaging gate passes;
4. target-provenance verification passes;
5. bounded-q verification passes;
6. predictive-witness verification passes;
7. evidence-semantics verification passes;
8. evidence-image verification passes;
9. support-envelope verification passes;
10. adjudicator verification passes;
11. R* maximality verification passes;
12. source and gate outputs are hashed into the CI artifact; and
13. the exact branch HEAD that contains the concrete implementation is the HEAD
    that passed those checks.

## 16. Trust boundaries deliberately not crossed

Concrete packaging still does not establish:

- physical/runtime adequacy of the finite TargetModel;
- conservative adequacy of the observation adapter to physical reality;
- raw runtime event -> canonical evidence-token correctness;
- concrete historical action -> modeled `ProjectedAction` realization integrity;
- target-native fallback behavior;
- retry/abort/evidence-acquisition policy;
- runtime E3b intervention;
- stochastic production q semantics;
- BDD/bitset optimization; or
- new experimental results.

In particular, a contract certifying REUSE is not permission for an execution
adapter to claim that an arbitrary concrete historical API call realizes the
certified projected action. That realization boundary remains explicit.

## 17. Next admitted boundary

After this concrete packaging gate closes, the semantic compiler itself is
provider-free and artifact-complete for the established finite deterministic
scope.

The next highest-value implementation boundary is no longer another semantic
compiler layer. It is the **runtime realization boundary**:

```text
raw retained observation
    -> canonical evidence token
historical concrete action
    -> verified ProjectedAction realization
CompiledContract
    -> semantic certificate
execution policy
    -> separately chosen reuse/fallback behavior
```

Those layers must remain separate so a live integration cannot smuggle
observation parsing, action identity, or fallback policy into the proved semantic
contract.
