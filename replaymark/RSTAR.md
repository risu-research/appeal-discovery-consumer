# ReplayMark `R*` — maximal certified reuse

## Scope

This increment implements exactly one theorem-induced binary boundary on top of
the already-frozen three-valued adjudicator:

```text
VALID       -> REUSE
INVALID     -> DO_NOT_REUSE
UNRESOLVED  -> DO_NOT_REUSE
```

Equivalently, for fixed retained evidence `e` and recorded claim-projected action
`z`:

`R*(e,z) = REUSE iff z in S_C^-(e)`.

This is **maximal certified reuse**, not a general execution policy.

`DO_NOT_REUSE` does not mean `REGENERATE`. It means only that the currently
retained evidence does not certify reuse of the historical action. A later system
may regenerate, obtain stronger evidence, abort, or use another target-supported
fallback. None of those choices is implemented or optimized here.

## Theorem versus policy

The theorem lives in a deliberately tiny decision space. A fixed-evidence binary
reuse rule sees only the semantic situation already represented by `(e,z)` and
chooses one of:

- `REUSE`; or
- `DO_NOT_REUSE`.

Call such a rule support-sound when every `REUSE` choice is supported in **every**
target world still compatible with `e`.

Since

`S_C^-(e) = intersection_{w in Omega(e)} S_C(w)`,

`REUSE` is sound exactly when `z in S_C^-(e)`.

Therefore `R*` is support-sound, and any other fixed-evidence support-sound rule
can reuse only a subset of the pairs reused by `R*`. Pointwise, under the order

`DO_NOT_REUSE < REUSE`,

`R*` selects the greatest sound choice at every `(e,z)`.

That is the theorem.

The following are **policy**, not theorem, and remain outside this branch:

- what action to execute after `DO_NOT_REUSE`;
- whether INVALID should immediately trigger target-native regeneration;
- whether UNRESOLVED should first trigger evidence acquisition;
- evidence-acquisition order;
- latency, energy, controller-invocation, or monetary cost optimization;
- abort/fallback rules; and
- stochastic distributional fidelity beyond support validity.

## Why INVALID and UNRESOLVED both map to DO_NOT_REUSE

For the reuse theorem, both states have the same consequence: historical reuse is
not certified.

- INVALID: no compatible target world supports the recorded action.
- UNRESOLVED: at least one compatible target world excludes the recorded action.

In both cases, reusing the historical action would violate fixed-evidence support
soundness in at least one admitted world.

The reasons remain scientifically different, so the production `RStarDecision`
preserves the original three-valued verdict even though its binary disposition is
the same. A later execution layer can therefore distinguish INVALID from
UNRESOLVED without contaminating the R* theorem.

## Production object

`replaymark.rstar.maximal_certified_reuse` consumes one sealed `Adjudication` and
returns an immutable `RStarDecision` containing:

- adjudication fingerprint;
- support-envelope fingerprint;
- claim fingerprint;
- evidence fingerprint;
- q depth;
- evidence token;
- exact claim-projected recorded action;
- original `Verdict`; and
- binary `ReuseDisposition`.

The certificate re-validates the exact theorem truth table:

- `Verdict.VALID` iff `ReuseDisposition.REUSE`;
- `Verdict.INVALID` or `Verdict.UNRESOLVED` iff
  `ReuseDisposition.DO_NOT_REUSE`.

There is no `REGENERATE`, `REFINE_EVIDENCE`, `ABORT`, or fallback method in this
semantic object.

## Independent raw-definition oracle

`replaymark_oracle.rstar_oracle` imports none of the production q,
evidence-image, support-envelope, adjudicator, or R* modules.

It computes R* directly from raw target worlds:

1. obtain `Omega(e)` from `EvidenceSpec`;
2. for each `w in Omega(e)`, evaluate `TargetModel.current_distribution(w)`;
3. retain only positive-mass target actions;
4. project them through the exact `ClaimSpec`;
5. test whether recorded projected `z` is supported in that world; and
6. return `REUSE` iff no compatible world excludes `z`.

For every `DO_NOT_REUSE` result the oracle records an excluding raw world. This is
not a production dependency; it is a constructive verification witness showing
that any policy which added reuse at that pair would be support-unsound.

The oracle also admits finite stochastic current supports. Production remains
bounded by the deterministic q pipeline until stochastic finite-horizon q is
separately proved.

## Canonical boundary cases

### N2b: reuse despite predictive ambiguity

The frozen Better Thermostat N2b pair has predictive-image cardinality
`1 -> 2 -> 2` for H=0,1,2, yet both compatible worlds currently support
`SET_AWAY`.

The adjudicator therefore remains VALID and R* returns REUSE at every tested
depth.

This is the constructive answer to an overconservative rule such as "regenerate
whenever raw or predictive state differs." Predictive distinction alone is not a
reason to discard a historical decision whose current consequence remains
certified.

### Mixed target worlds: no certified reuse

Evidence admitting one `SET_HOME` world and one at-target `NO_ACTION` world makes
both recorded `SET_HOME` and `NO_ACTION` UNRESOLVED; recorded `SET_AWAY` is
INVALID.

R* returns DO_NOT_REUSE for all three, while preserving whether the reason was
UNRESOLVED or INVALID.

With stronger single-world evidence selecting the `SET_HOME` world, `SET_HOME`
becomes VALID and R* becomes REUSE.

### Stochastic support boundary

An oracle-only fixture with raw-world supports `{A,B}` and `{B,C}` gives:

- `B -> REUSE` because every compatible world supports B;
- `A -> DO_NOT_REUSE` with the second world as a counterexample; and
- an explicit zero-mass action `ZERO -> DO_NOT_REUSE` with both worlds excluding
  it.

This is support validity only; it does not claim that reusing B preserves the
stochastic target distribution.

## Maximality verification strategy

The strongest practical verification is pointwise rather than enumerating every
global policy function.

At each `(e,z)` there are only two binary choices. `DO_NOT_REUSE` is always
support-sound because it makes no reuse claim. `REUSE` is support-sound iff every
compatible raw world supports `z`.

Therefore:

- if no raw world excludes `z`, both choices are sound and R* chooses the greater
  one, REUSE;
- if at least one raw world excludes `z`, only DO_NOT_REUSE is sound, and the
  excluding world is a constructive witness against any extra reuse.

This establishes pointwise maximality directly and avoids testing a weaker proxy
such as mere agreement with the three-valued verdict table.

## Verification gate

This branch requires all previous semantic gates to remain green and additionally
checks:

1. production R* against a completely independent raw-world oracle on all
   thermostat boundary cases;
2. N2b retaining REUSE across predictive-image refinement `1 -> 2 -> 2`;
3. INVALID and UNRESOLVED both yielding DO_NOT_REUSE while preserving distinct
   verdicts in the certificate;
4. stronger evidence turning a previously uncertified historical action into
   certified REUSE when all remaining worlds agree;
5. invariance to recorded coordinates outside the benchmark claim;
6. an intentionally tiny binary disposition surface with no regeneration or
   evidence-refinement operation;
7. rejection of a theorem-inconsistent forged R* certificate;
8. stochastic raw-definition checks including explicit zero probability;
9. exhaustive differential verification over all **5,832** complete 3-state /
   2-continuation / 2-output deterministic machines, all seven nonempty evidence
   subsets, and both recorded actions: **81,648** production-vs-raw-oracle R*
   decisions;
10. a constructive excluding-world witness for every non-reusable exhaustive
    pair, proving that each attempted additional reuse would be unsound; and
11. every strict evidence-refinement relation for both candidate actions,
    checking that once reuse is certified it cannot be lost under stronger
    evidence: **139,968** refinement-persistence checks.

The expected exhaustive split inherited from the frozen adjudicator gate is:

- REUSE: **27,702**;
- DO_NOT_REUSE: **53,946**;
- pointwise maximality checks: **81,648**; and
- blocked pairs carrying at least one raw counterexample: **53,946**.

## Claims explicitly not made

This implementation does not establish that R* is:

- globally cost-optimal;
- a complete replay engine;
- always faster than target-native regeneration;
- always cheaper in controller invocations;
- a stochastic distribution-preservation mechanism; or
- a rule for which fallback action to execute.

Its exact claim is narrower and stronger:

> Given the current retained evidence and a support-validity claim, R* reuses
> exactly the historical actions whose reuse is certified in every target world
> that evidence still admits; no other fixed-evidence support-sound binary policy
> can certify reuse on any additional pair.

## Next boundary

Only after R* is frozen should ReplayMark instantiate the concrete
`CompiledContract` that packages the already-verified q, evidence, support,
adjudication, and maximal-reuse artifacts for cheap runtime use.

That future contract may expose R* to a runtime caller, but the caller's fallback
policy and live E3b intervention remain separate subsequent steps.
