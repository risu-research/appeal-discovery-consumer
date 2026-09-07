# ReplayMark bounded `q_{C,H}` compiler + independent definition oracle

## Scientific object

For a declared claim `C` and consequence horizon `H`, two target decision histories are in the same `q_{C,H}` class iff their current `C`-projected outputs are identical and every admitted future continuation word of length at most `H` induces identical `C`-projected output behavior.

Compiler v1 closes this object for finite deterministic two-phase `TargetModel`s. The minimization substrate is established automata machinery; ReplayMark's contribution is the claim/horizon-typed use of the quotient inside the replay-sufficiency factorization, not a new generic minimization theorem.

## Production algorithm

Let `P_0` group decision states by the current `ClaimSpec`-projected output. For `h>=1`, form each state's signature from its current projected output and, for every admitted continuation symbol, the `P_{h-1}` block reached after the current decision and that continuation. Group equal signatures to obtain `P_h`. Compile **only** `P_0 ... P_H`.

This is bounded Moore-style refinement. Canonical block IDs are derived from canonical sorted member sets, so incidental dictionary traversal does not define scientific identity.

The result records every partition layer, current projected actions, deterministic continuation successors actually consumed inside the requested horizon, claim and target fingerprints, canonical bytes/result fingerprint, and the first fixed point only if equality of adjacent computed layers was observed.

It does **not** yet contain evidence support masks or runtime reuse guards.

## Independent definition oracle

The oracle intentionally uses a different computational path. For each target decision state and every continuation word up to `H`, it directly expands the target's exact probability tree and computes the exact `Fraction`-valued law over projected output traces. Two states are grouped only when all of those word-indexed laws are equal.

This path is intentionally slower and exponential in `H`. Its job is not production performance; it is to make the mathematical definition executable with minimal algorithmic cleverness.

Because the oracle evaluates exact trace laws, it can represent stochastic targets. That capability is used as a red-team boundary: compiler v1 must reject stochastic targets rather than silently assign them a stronger or different equivalence semantics.

## Why the model is two-phase

A target prediction step is:

```text
current decision condition
  -> current action + post-decision latent/controller state
  -> one admitted future continuation
  -> next decision condition
```

This exactly realizes both frozen canonical cases:

- E3b: the current feedback belongs to the current decision condition; a future feedback symbol is chosen only after the current action updates the controller state.
- Better Thermostat: the current presence/motion/night/preset tuple already determines the current output; the current controller action settles the preset, then a future trigger changes one environmental bit before the next decision.

Collapsing those two phases into `distribution(state, input)` would make it ambiguous whether the supplied input is current evidence or a future continuation and can produce the wrong q domain.

## Correctness gates

The verification suite uses the real frozen legacy kernel adapter for E3b and a verification-only exact restatement of the already-frozen thermostat q model. It then runs an exhaustive compiler-vs-oracle differential gate over all complete deterministic machines with 3 decision states, 2 continuation symbols, 2 output symbols, all 8 output assignments, all `3^(3*2)=729` transition functions, and horizons 0, 1, 2, and 3.

That is **5,832 machines** and **23,328 horizon-indexed partition-relation comparisons**. The test compares pairwise equivalence relations, not implementation-specific block numbers.

The suite also checks the frozen canonical results:

- E3b: `3,3,3,3`;
- Better Thermostat: `5,14,16,16,16`;
- first observed thermostat fixed point: depth 2 only when H>=3 has actually been compiled;
- N2b shortest word: `presence_toggle`;
- independent depth-2 word: `presence_toggle, night_toggle`;
- 56-state seven-preset model: 16 classes at the stable relation.

## Explicit nonclaims

This stage does not claim a new Moore/Nerode/partition-refinement theorem, stochastic q compilation, evidence sufficiency, a three-valued replay verdict, maximal selective reuse, runtime overhead/scalability, Home Assistant semantics extraction, or a new live experiment.

Those are separate obligations and will not be smuggled into this compiler stage.
