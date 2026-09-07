# ReplayMark compiler-observed target semantic provenance

## 1. The provenance hole

Before this increment, `BoundedQuotient` recorded `TargetModel.fingerprint`.
That value is useful provider metadata, but it is not a trustworthy semantic
commitment. A provider can accidentally reuse the same fingerprint after its
behavior changes, forget to update it, or compute it from a representation that
omits consequential semantics.

The dangerous failure is not a hash collision. It is a stale or incomplete
**provider assertion** being mistaken for compiler-observed semantic identity.

ReplayMark now keeps the provider fingerprint, but no longer treats it as the
semantic provenance authority.

## 2. Snapshot first, compile second

The high-assurance shape is:

```text
TargetModel provider
      |
      v
observe complete finite two-phase semantics
      |
      v
ObservedTargetSemantics  -- compiler-derived semantic digest
      |
      v
claim projection + bounded q compilation
```

`compile_bounded_q()` first calls `observe_target_semantics()`. The q compiler
then consumes the immutable snapshot and does **not re-query the TargetModel**.

This is stronger than merely calculating a hash beside the old compiler. It
closes a time-of-check/time-of-use gap: the digest and q quotient are derived
from the same observed laws.

## 3. What the compiler observes

ReplayMark enumerates the finite two-phase model independently of the benchmark
claim:

```text
decision_state
  -- current_distribution --> (full ProjectedAction, post_state)
post_state
  -- advance_distribution(continuation) --> next decision_state
```

The snapshot includes:

- every declared decision-state identifier;
- the declared continuation symbols;
- every positive-probability current branch, including the **full unprojected**
  `ProjectedAction`, post-state, and exact rational mass;
- every positive post-state induced by a current law;
- for every such post-state and every declared continuation symbol, the exact
  positive-probability next-decision-state law.

The observation is therefore claim-independent. Two different `ClaimSpec`s over
the same target share one target semantic digest even when their q partitions
are different.

## 4. Semantic identity versus artifact identity

ReplayMark intentionally distinguishes two identities.

### Compiler-observed semantic digest

`semantic_digest` commits only to modeled target behavior.

It is invariant to:

- provider fingerprint text;
- decision-state enumeration order;
- mapping insertion order;
- explicit zero-probability branches; and
- declared continuation **ordering** when the named continuation-to-transition
  relation is unchanged.

The last point is deliberate. Continuation order is a deterministic
canonicalization/tie-break policy for choosing among equally short predictive
witnesses; it is not a change in the underlying labeled transition semantics.

### Snapshot fingerprint

`ObservedTargetSemantics.fingerprint()` commits to the complete artifact,
including:

- provider fingerprint metadata;
- declared continuation order; and
- the compiler-observed semantic snapshot.

Thus two semantically identical providers may have the same semantic digest but
different snapshot fingerprints. That is expected and useful.

## 5. Component digests

The semantic root is decomposed into named compiler-derived components:

- `domain_digest`: decision-state identifiers + continuation symbols;
- `current_semantics_digest`: full current action/post-state probability laws;
- `advance_semantics_digest`: post-state/continuation next-state probability laws;
- `semantic_digest`: a named root over the three component digests.

This is not needed for collision resistance; one flat hash would suffice.
The decomposition is for auditability. If a target changes, ReplayMark can tell
whether the change was in the domain, current controller decision semantics, or
future transition semantics.

## 6. Positive-law semantics

The digest is over exact **positive-probability semantics**.

An explicit branch with probability zero does not change the semantic digest.
This matches ReplayMark's support semantics and exact trace-law definitions:
zero-mass dictionary entries are representation artifacts, not admitted behavior.

Positive probability masses are serialized as exact numerator/denominator pairs.
A change from `1/2` to `1/3`, even with the same support set, changes the current
semantic digest and therefore the semantic root.

This layer can therefore provenance stochastic TargetModels even though the
current production q compiler still fails closed on stochastic branching.
Provenance support is not a claim that stochastic q compilation has been proved.

## 7. Stability and completeness checks

A content digest is useful only if the adapter behaves like a stable semantic
model during compilation. ReplayMark therefore observes the target twice:

- first in canonical decision/continuation order;
- then with decision states and continuations queried in the opposite order.

The compiler rejects the model if:

- provider fingerprint changes during observation;
- the decision-state domain changes;
- declared continuation order changes;
- any current law changes;
- any advance law changes;
- a probability law does not sum exactly to one;
- a positive current branch is malformed;
- a positive transition reaches an undeclared decision state; or
- any positive post-state/continuation pair lacks semantics.

This catches accidental stateful/order-dependent adapters before they can be
certified.

## 8. Provider fingerprint is retained, but demoted

`BoundedQuotient.target_model_fingerprint` is retained for compatibility and is
now explicitly a **provider-supplied metadata field**. `provider_fingerprint` is
a readable alias.

The provenance authority is:

`BoundedQuotient.target_semantic_digest`.

The quotient also carries the snapshot fingerprint and the three component
digests. A stale provider label can therefore no longer hide a target semantic
change from a compiled q artifact.

## 9. Independent definition oracle

`replaymark_oracle.target_provenance_oracle` does not import the production
provenance compiler. It independently enumerates positive current/advance laws,
canonicalizes them, and computes the named domain/current/advance/root digests.

This is an algorithmically independent canonicalization oracle above the shared
`TargetModel` semantic TCB. It verifies the provenance compiler; it does not
prove that the TargetModel accurately represents a physical system.

## 10. Verification gates

This increment is admitted only if all of the following hold:

1. identical target semantics with different provider fingerprints produce the
   same semantic digest;
2. changed semantics under the same stale provider fingerprint produce a
   different semantic digest;
3. decision-state order, mapping insertion order, and explicit zero-mass
   branches do not change the semantic digest;
4. continuation-order reversal with unchanged labeled transitions preserves the
   semantic digest but changes snapshot identity/tie-break metadata;
5. current-only and advance-only mutations change the corresponding component
   digest and the root while leaving unrelated components unchanged;
6. exact stochastic probability changes alter the semantic digest;
7. stateful target adapters fail closed;
8. a forged snapshot root is rejected by the artifact's own validation;
9. the bounded q compiler embeds exactly the digest of the snapshot from which
   it compiled;
10. different claims over one target share target provenance while still being
    free to produce different q partitions;
11. Better Thermostat preserves the frozen `5 -> 14 -> 16 -> 16 -> 16` q result;
12. all **5,832** labeled complete 3-state/2-continuation/2-output deterministic
    machines agree with the independent provenance oracle; and
13. even when all 5,832 models are deliberately given the **same provider
    fingerprint**, all 5,832 distinct labeled semantics receive distinct
    compiler-observed semantic digests.

All earlier semantic gates are rerun after the q compiler is migrated to
snapshot-first compilation.

## 11. What this still does not prove

The semantic digest proves identity of the **modeled** finite TargetModel that
ReplayMark observed. It does not prove that:

- the TargetModel is an adequate model of the physical/runtime system;
- a concrete historical action realizes the same target-side transition as the
  projected action;
- runtime raw observations are canonicalized correctly; or
- the final CompiledContract API is already frozen.

Those are separate trust boundaries and must not be smuggled into this digest.

## 12. Next boundary

After this provenance hardening, the remaining pre-packaging step is to re-freeze
the `CompiledContract` API around the semantics actually established:

- predictive continuation witnesses;
- R* counterexample worlds;
- compiler-owned evidence semantics;
- compiler-observed target semantic provenance; and
- three-valued adjudication / maximal certified reuse.

No runtime fallback policy or live intervention belongs in that API re-freeze.
