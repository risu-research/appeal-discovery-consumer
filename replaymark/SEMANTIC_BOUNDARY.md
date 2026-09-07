# ReplayMark semantic boundary — target-provenance hardening freeze

**Status:** bounded `q_{C,H}`, compiler-owned evidence semantics, q evidence image,
deterministic support envelope, three-valued adjudication, maximal certified
reuse `R*`, and production predictive continuation witnesses are implemented and
independently gated. This branch adds compiler-observed target semantic
provenance and migrates q compilation to snapshot-first semantics.  
**Predictive-witness authority:** `replaymark-predictive-witness@067eadbf938e58170aebff883b4ab0c8e085e9cd`.  
**Current branch scope:** demote provider fingerprint to metadata; enumerate,
stability-check, and content-address the complete finite two-phase TargetModel;
then compile q from exactly that sealed snapshot.  
**Still out of scope:** final `CompiledContract` API re-freeze/implementation,
runtime raw-observation canonicalizer, concrete historical-action realization
obligation, target-native fallback policy, runtime E3b gate, stochastic q
compilation, BDD/bitset optimization, and new live experiments.

## 1. Executable semantic chain

The production semantic chain is:

`TargetModel -> ObservedTargetSemantics -> ClaimSpec -> q_{C,H}`

then:

`CompiledEvidenceSemantics -> q[Omega(e)] -> S-/S+ -> VALID/INVALID/UNRESOLVED -> R*`.

Predictive continuation witnesses are compiled from the sealed q artifact and
remain separate from R* counterexample worlds.

## 2. Target semantics

ReplayMark uses a finite two-phase target model:

```text
decision_state
    -- current_distribution --> (full action, post-decision state)
post-decision state
    -- advance_distribution(future continuation) --> next decision_state
```

The public TargetModel can represent exact rational stochastic laws. Production
bounded-q compilation remains deterministic and input-enabled over the declared
continuation alphabet. Stochastic models are not silently assigned a production
q semantics.

## 3. Compiler-observed target provenance

`TargetModel.fingerprint` is retained as provider metadata but is no longer the
semantic provenance authority.

Before q compilation, ReplayMark observes and seals:

- every declared decision state;
- every continuation symbol;
- every positive current `(full ProjectedAction, post_state, exact mass)` branch;
- every positive post-state induced by those current laws; and
- every positive next-decision-state law for each positive post-state x declared
  continuation symbol.

The resulting `ObservedTargetSemantics.semantic_digest` is compiler-derived.
`compile_bounded_q()` then consumes only that snapshot rather than re-querying the
TargetModel, binding q to the exact semantics that were hashed.

The digest is claim-independent: full action coordinates are observed before
`ClaimSpec.project()` is applied.

## 4. Semantic digest versus snapshot fingerprint

ReplayMark deliberately separates behavioral identity from artifact metadata.

The **semantic digest** is invariant to provider fingerprint text, target state
enumeration order, mapping insertion order, explicit zero-mass branches, and a
mere permutation of the declared continuation order when the named transition
relation is unchanged.

The **snapshot fingerprint** additionally binds provider metadata and declared
continuation order. Continuation order matters to deterministic tie-breaking
among equally short predictive witnesses, but is not itself a change in the
labeled target behavior.

The semantic root is decomposed into compiler-derived domain/current/advance
digests so semantic changes can be localized during audit.

## 5. Provenance stability checks

Target observation is executed twice using opposite query orders. Compilation
fails closed if the provider fingerprint, state domain, continuation order,
current laws, or advance laws change between passes.

Exact probability laws must sum to one. Positive branches must be well formed,
and positive advance branches must remain inside the declared decision-state
domain. Every positive post-state x declared continuation pair must have total
semantics.

Zero-mass entries are intentionally excluded from semantic identity.

## 6. Bounded claim-predictive state

After provenance observation, production computes exactly the declared finite
horizon:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for every admitted u)`.

No hidden `H+1` lookahead is used. The q definition oracle independently
enumerates continuation words and projected output-trace laws.

`BoundedQuotient` records both the provider fingerprint and the compiler-observed
semantic/snapshot/component digests. The provider fingerprint is explicitly not
used as the semantic authority.

## 7. Predictive witness semantics

A predictive continuation witness answers why two worlds lie in different
`q_{C,H}` classes. It is the shortest admitted continuation word whose projected
output traces differ.

Production derives shortest witnesses from first-separation q refinement
backpointers. The independent definition oracle instead enumerates words by
length and evaluates exact trace laws.

A current-output difference has the empty word as its shortest witness.

Predictive witnesses contain no evidence token, historical action, support
verdict, or reuse decision.

## 8. Evidence semantics: forward relation is authoritative

Production authoring supplies:

`O(w) = set of retained-evidence tokens possible in modeled world w`.

ReplayMark enumerates every target decision world and computes:

`Omega(e) = { w : e in O(w) }`.

Users/adapters do not manually enumerate `Omega(e)` on the certification path.
A deterministic observation is a singleton `O(w)`; partial/noisy/multi-mode
evidence may return several tokens.

For support-sound reuse the external adapter obligation is conservative
completeness:

`O_real(w) subseteq O_model(w)`

or equivalently `Omega_real(e) subseteq Omega_model(e)`.

Over-approximation may reduce reuse but does not hide a real counterexample.

## 9. Evidence image and support envelope

For each observation token:

`I_{C,h}(e) = q_{C,h}[Omega(e)]`.

Then:

`S_C^-(e) = intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) = union_{w in Omega(e)} S_C(w)`.

Production verifies current-support constancy inside deterministic q blocks. The
raw support oracle bypasses compiled q/evidence artifacts and evaluates raw worlds
directly.

## 10. Three-valued adjudication

For recorded claim-projected action `z`:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` otherwise.

UNRESOLVED is semantic underdetermination, not a confidence score.

## 11. Maximal certified reuse R*

For fixed evidence and support validity:

`R*(e,z) = REUSE iff z in S_C^-(e)`.

Thus:

- `VALID -> REUSE`;
- `INVALID -> DO_NOT_REUSE`;
- `UNRESOLVED -> DO_NOT_REUSE`.

`DO_NOT_REUSE` is not a regeneration command. Fallback remains policy. R* is
pointwise maximal among fixed-evidence binary support-sound reuse rules.

An R* counterexample is one raw world in `Omega(e)` that excludes `z`; it is not
a predictive continuation witness and has no shortest-continuation semantics.

## 12. Verification independence and TCB

The project uses algorithmically independent definition oracles above shared
semantic contracts:

- q production: bounded partition refinement; q oracle: literal continuation-word
  trace laws;
- predictive witness production: refinement backpointers; witness oracle: literal
  shortest-word enumeration;
- evidence closure production: compiler-owned forward inversion; evidence oracle:
  literal inverse relation;
- support/adjudication/R* production: compiled intermediate artifacts; raw oracles:
  direct compatible-world support evaluation;
- target provenance production: stable two-pass semantic snapshot; provenance
  oracle: independent one-pass positive-law canonicalization and digesting.

These oracles verify implementation fidelity. They do not prove that TargetModel
or observation adapters are adequate models of physical reality.

## 13. Admitted target-provenance verification

This branch is closed only if:

- same semantics under different provider fingerprints produce the same semantic
  digest;
- changed semantics under the same stale provider fingerprint change the digest;
- state/dictionary order and zero-mass representation do not change the digest;
- continuation-order permutation preserves semantic identity while remaining
  visible in snapshot identity;
- current-only and advance-only mutations change the corresponding component
  digest and root;
- exact probability changes change semantic identity;
- stateful/order-dependent TargetModels fail closed;
- forged semantic roots are rejected by the snapshot object;
- q embeds exactly the digest of the snapshot it consumed;
- different ClaimSpecs over one target share target provenance while allowing
  different q partitions;
- Better Thermostat preserves the frozen `5 -> 14 -> 16 -> 16 -> 16` result;
- all 5,832 complete labeled 3-state/2-continuation/2-output deterministic
  machines agree with an independent provenance oracle; and
- giving all 5,832 models the same provider fingerprint still yields 5,832
  distinct compiler-observed semantic digests.

All prior semantic gates must remain green after snapshot-first q migration.

## 14. Remaining trust boundaries

The compiler-observed digest proves identity of the **modeled finite target**.
It does not prove:

- physical/runtime model adequacy;
- runtime raw-observation canonicalization;
- equivalence between a concrete historical action realization and the modeled
  target-side transition; or
- any fallback execution policy.

Those must remain explicit rather than being hidden under the word provenance.

## 15. Next boundary

Do not add runtime intervention yet.

The remaining pre-packaging step is to re-freeze the `CompiledContract` API around
the semantics now actually established. In particular, the provisional generic
`shortest_witness(observation, historical_action)` seed must be replaced by
separate predictive-witness and R* counterexample operations, and the contract
must expose compiler-owned evidence and target-provenance bindings directly.
