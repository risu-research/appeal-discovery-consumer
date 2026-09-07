# ReplayMark three-valued support adjudicator

## Scope

This increment implements exactly one new semantic arrow:

`(recorded action z, S_C^-(e), S_C^+(e)) -> VALID / INVALID / UNRESOLVED`.

For the exact support envelope already compiled for evidence `e`:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` iff `z in S_C^+(e) \\ S_C^-(e)`.

These three cases are mutually exclusive and exhaustive because
`S_C^-(e) subseteq S_C^+(e)`.

This branch does **not** map a verdict to `REUSE`, `REGENERATE`, evidence
acquisition, abort, or any other operational policy. In particular, it does not
implement maximal reuse `R*`. Adjudication answers only what the current semantic
evidence establishes about the recorded action.

## Why adjudication is a separate layer

A support envelope is a property of target uncertainty under one evidence token.
A verdict is a property of one **recorded action relative to that envelope**.
Keeping these objects separate has three advantages:

1. one compiled envelope can adjudicate many candidate historical actions;
2. support construction can be verified independently from membership logic; and
3. policy cannot silently enter the semantic certificate.

`UNRESOLVED` is therefore not an implementation error, confidence score, or
probabilistic guess. It is the exact case in which some target worlds still
compatible with the same evidence support the recorded action and others exclude
it.

## Production interface

`replaymark.adjudicator.adjudicate_support` consumes:

- a sealed `SupportEnvelope`;
- the exact `ClaimSpec` whose fingerprint is sealed into that envelope;
- one evidence observation token; and
- one canonical `ProjectedAction` from the recorded execution.

The recorded action may contain adapter coordinates beyond the benchmark claim.
The adjudicator first applies the exact `ClaimSpec` projection. Thus irrelevant
coordinates cannot alter scientific identity, while a missing required dimension
fails closed.

Before membership testing, production checks the local support artifact
invariants required by the theorem:

- nonempty predictive q image;
- nonempty possible support;
- no duplicate support actions;
- `S^- subseteq S^+`; and
- every support action has exactly the claim-declared dimensions.

A foreign ClaimSpec, malformed envelope row, unknown evidence token, or missing
claim-required recorded-action dimension is rejected.

## Adjudication certificate

The returned `Adjudication` records only semantic facts:

- support-envelope fingerprint;
- claim and evidence fingerprints;
- q depth;
- evidence token;
- claim-projected recorded action;
- membership in `S^-` and `S^+`; and
- the exact three-valued `Verdict`.

The dataclass re-validates the verdict/membership truth table on construction.
It exposes no `may_reuse`, `regenerate`, or similar policy method.

Because the certificate records only the claim-projected action, two raw recorded
actions that differ solely in non-consequential coordinates compile to identical
canonical adjudication bytes.

## Completely independent definition oracle

`replaymark_oracle.adjudication_oracle` imports none of the production q,
evidence-image, support-envelope, or adjudicator modules.

For each raw world `w in Omega(e)`, it directly evaluates
`TargetModel.current_distribution(w)`, keeps only positive-mass target actions,
projects them through `ClaimSpec`, and asks whether the recorded projected action
is supported in that world.

It then returns:

- `VALID` if every compatible raw world supports the action;
- `INVALID` if no compatible raw world supports it; or
- `UNRESOLVED` otherwise.

For verification diagnostics only, the oracle records the supporting and
excluding raw worlds. Production does not depend on those witness sets.

The oracle supports finite stochastic current decisions. This is intentional:
the three-valued support theorem is about positive support, even though the
production q pipeline remains deterministic until a stochastic q compiler is
separately proved.

## Canonical boundary cases

The frozen Better Thermostat cases instantiate all three verdicts.

### Valid despite predictive ambiguity

The N2b pair has q evidence-image cardinality `1 -> 2 -> 2` across H=0,1,2, but
both compatible worlds currently support `SET_AWAY`. Therefore the recorded
`SET_AWAY` is `VALID` at every tested depth.

This proves that multiple predictive worlds do not by themselves imply an
unresolved current action.

### Unresolved under mixed target worlds

Evidence admitting one world that emits `SET_HOME` and one at-target world that
emits `NO_ACTION` gives `S^- = empty` and
`S^+ = {SET_HOME, NO_ACTION}`. A recorded `SET_HOME` is therefore `UNRESOLVED`;
so is a recorded `NO_ACTION`.

### Invalid outside possible support

Under the same mixed evidence, `SET_AWAY` is outside `S^+` and is therefore
`INVALID`.

With stronger single-world evidence selecting the `SET_HOME` world, `SET_HOME`
becomes `VALID` while `NO_ACTION` becomes `INVALID`.

## Stochastic definition boundary

An oracle-only stochastic fixture uses compatible-world supports `{A,B}` and
`{B,C}` plus an explicit zero-mass action `ZERO` in both target distributions.
The exact verdicts are:

- recorded `B`: `VALID`;
- recorded `A`: `UNRESOLVED`;
- recorded `ZERO`: `INVALID`.

The last case verifies that merely appearing as a zero-probability distribution
key does not make an action part of target support.

## Verification

The branch requires all earlier semantic gates to remain green and adds:

1. production-vs-independent-raw-oracle agreement for all canonical thermostat
   VALID/INVALID/UNRESOLVED cases;
2. N2b `SET_AWAY` remaining `VALID` while its predictive q image refines
   `1 -> 2 -> 2`;
3. exact mixed-world UNRESOLVED and outside-`S^+` INVALID cases;
4. stronger-evidence transition to exact VALID/INVALID outcomes;
5. projection invariance under extra non-claim recorded-action coordinates;
6. fail-closed claim fingerprint binding, missing dimensions, unknown evidence,
   and malformed `S^- not subseteq S^+` input;
7. stochastic raw-definition trichotomy with an explicit zero-mass action; and
8. exhaustive differential adjudication over all **5,832** complete
   3-state / 2-continuation / 2-output deterministic machines at H=2, all seven
   nonempty evidence subsets, and both recorded output actions: **81,648** exact
   production-vs-definition adjudications, with all three verdicts required to
   occur.

## Next boundary

Only after this three-valued adjudication layer is frozen may a later branch map
semantic verdicts into a replay policy. The natural next theorem-induced object
is maximal certified reuse `R*`, but that policy must remain separate from this
adjudicator so that semantic validity is not conflated with an execution choice.
