# ReplayMark evidence-semantics closure

## 1. The hole being closed

Before this increment, `EvidenceSpec` was an explicit inverse map:

`e -> Omega(e)`.

That representation is mathematically sufficient but unsafe as a production
authoring interface. An adapter author could accidentally omit a target world
from `Omega(e)`. Every downstream theorem could then be implemented perfectly
and still certify a false REUSE because the missing world was never considered.

The fix is not a more complicated adjudicator. It is to change who owns the
inverse relation.

## 2. Forward authoring, compiler-owned inversion

Production evidence is now authored in the forward direction:

`O(w) = set of retained-evidence tokens that may arise in modeled world w`.

`ObservationSupportModel.observation_support(w)` supplies this finite support.
ReplayMark enumerates every declared target decision world and derives:

`Omega(e) := { w : e in O(w) }`.

The user/adapter author therefore **does not enumerate Omega(e)**. The compiler
owns the inversion and seals both directions of the relation.

A deterministic observation projection is the common special case:

`O(w) = { observe(w) }`.

Partial, noisy, or multi-mode retained evidence can be represented without a new
theorem by returning several possible tokens from one world.

## 3. What is actually guaranteed

There are two distinct guarantees and they must not be conflated.

### Compiler guarantee: mechanical closure

Relative to the finite `TargetModel` world domain and the supplied forward
observation relation, ReplayMark guarantees that:

- every declared target world is queried;
- every modeled world has at least one explicit evidence interpretation;
- every returned `(world, token)` edge is included in the compiled relation;
- `Omega(e)` is the exact inverse image of those edges;
- the forward and inverse forms are re-checked against each other;
- the adapter is queried twice in opposite world orders and must be referentially
  stable; and
- a hand-authored `EvidenceSpec` is rejected by the production evidence-image
  boundary.

Thus a compatible world cannot be lost by an inversion/list-construction bug or
by forgetting to list it manually in `Omega(e)`.

### Adapter/model guarantee: semantic adequacy

No finite compiler can prove from first principles that an observation adapter
faithfully describes a physical sensor, Home Assistant state, network observer,
or external evidence source. That is a model-validation obligation.

For support-sound reuse the required direction is **conservative completeness**.
If `O_real(w)` is the set of evidence tokens the real retained-evidence mechanism
could produce, the modeled relation should satisfy:

`O_real(w) subseteq O_model(w)`

for every admitted world. Equivalently:

`Omega_real(e) subseteq Omega_model(e)`.

Over-approximation is safe for the support theorem: it may create more
UNRESOLVED/DO_NOT_REUSE outcomes, but it cannot create a false certification by
removing a real counterexample world. Under-approximation is the dangerous
failure mode and must be prevented by adapter construction/validation.

When the adapter is uncertain, it should model more possibilities rather than
silently omit them.

## 4. `EvidenceSpec` is now low-level IR, not production authoring

`EvidenceSpec` remains useful as the canonical extensional inverse relation and
as a definition-oracle/test object. Existing mathematical oracles consume it
because the theorem itself is naturally stated over `Omega(e)`.

Production certification, however, no longer accepts a naked `EvidenceSpec` at
the evidence-image boundary. It requires `CompiledEvidenceSemantics`, which is
created only by forward-relation compilation.

Historical hand-authored inverse fixtures are retained only in
`replaymark_verification`. A verification helper converts each expected inverse
fixture into a total forward relation, recompiles it, and checks that ReplayMark
re-derives the expected named `Omega(e)` sets. This preserves prior scientific
gates without reopening the production bypass.

## 5. Sealed artifact

`CompiledEvidenceSemantics` records:

- evidence identity;
- every target decision-world identifier;
- every world's canonical observation support;
- a compiler-derived target-domain fingerprint;
- a compiler-derived observation-relation fingerprint; and
- the exact derived `EvidenceSpec` inverse.

The object re-derives and validates the inverse in `__post_init__`. Its relation
fingerprint is computed from the enumerated relation rather than trusted from an
adapter-provided hash.

This stage deliberately does not solve general target-model provenance; that is a
separate hardening item. It does remove provider-controlled provenance from the
evidence relation itself.

## 6. Why a forward relation is preferable to the alternatives

Several alternatives were considered.

**Manual inverse map `e -> worlds`.** Simple but leaves the original omission
hazard and scales poorly to overlapping/noisy observations.

**Predicate `compatible(world,e)`.** Better than manual sets because the compiler
can enumerate worlds for a token, but it requires a declared observation alphabet
and makes it easier to forget possible tokens. It is useful as a future symbolic
backend but is not the cleanest finite authoring direction.

**Deterministic observation function `world -> token`.** Excellent for exact
projections but too narrow for noisy/partial/multi-mode evidence.

**Forward support relation `world -> set(tokens)`.** Strictly generalizes the
deterministic function, allows conservative over-approximation naturally, lets
the compiler derive the token alphabet and all inverse images, and keeps the
current support-validity theorem unchanged. This is the chosen v1 boundary.

A future symbolic relation/BDD backend may implement the same semantics without
changing the meaning of `Omega(e)`.

## 7. Better Thermostat closure example

The verification model exposes two retained-evidence modes from every thermostat
world:

- `hide-motion`: retain presence, night, and current preset;
- `hide-preset`: retain presence, motion, and night.

The compiler derives the N2b `hide-motion` token to exactly two worlds, differing
only in motion. No pair is manually listed.

For `hide-preset` at presence=true, motion=false, night=false, the compiler derives
**four** worlds because all four current preset values are compatible. This is an
important audit result: a minimal two-world witness is not automatically a
complete observation class. The complete four-world class still yields the
expected support boundary (`SET_HOME` unresolved; `SET_AWAY` invalid), but now
that conclusion is based on the full compiler-derived epistemic set.

## 8. Verification strategy

The closure gate includes:

1. an independent literal inversion oracle that imports no production evidence
   compiler;
2. exhaustive enumeration of all `7^3 = 343` total nonempty relations from three
   target worlds to nonempty subsets of three evidence tokens;
3. bidirectional edge checks for every compiled relation;
4. the Better Thermostat forward-observation example above, followed through the
   existing q/support/adjudication/R* chain;
5. a deliberate manual-omission trap in which hand-authoring would omit a third
   counterexample world; production rejects the manual inverse and the compiler
   derives all three worlds, changing the result to UNRESOLVED;
6. a conservative-overapproximation check;
7. rejection of an uncovered modeled world;
8. rejection of duplicate observation tokens;
9. rejection of noncanonical mutable return shape; and
10. rejection of stateful/order-dependent observation semantics.

The new workflow also reruns every previously frozen semantic gate after migrating
production evidence-image calls to compiler-derived evidence.

## 9. Trusted computing boundary after this step

The evidence inversion itself is no longer trusted author input.

The remaining evidence TCB is deliberately smaller:

- the declared `TargetModel` world domain;
- the semantics of `ObservationSupportModel.observation_support(w)`; and
- later, a runtime raw-observation canonicalizer that must emit the same compiled
  token vocabulary.

The third item is not implemented in this increment. Until runtime integration,
this branch closes compile-time epistemic semantics only.

The observation adapter should preferably be generated from declarative state
projection or validated against raw-system traces. Where exactness is uncertain,
conservative over-approximation is the scientifically safe choice.

## 10. Next boundary

Do **not** package the final `CompiledContract` yet.

After this closure, the remaining pre-packaging hardening items are still:

1. split predictive continuation witnesses from reuse counterexample worlds and
   implement the production predictive witness path;
2. add compiler-observed target-semantic provenance rather than relying only on a
   provider fingerprint; and
3. re-freeze the `CompiledContract` API using the semantics actually learned.

Those are separate increments. This branch changes only who owns and certifies
`Omega(e)`.
