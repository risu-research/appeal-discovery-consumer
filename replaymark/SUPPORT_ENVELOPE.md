# ReplayMark support-envelope compiler: `S_C^-(e)` / `S_C^+(e)`

## Scope

This increment implements exactly one new semantic arrow:

`q_{C,H}[Omega(e)] -> S_C^-(e), S_C^+(e)`.

For each evidence token `e`, the already-frozen `EvidenceSpec` denotes the
nonempty set `Omega(e)` of compatible target decision worlds. Each world has
claim-projected current support `S_C(w)`. ReplayMark defines:

`S_C^-(e) = intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) = union_{w in Omega(e)} S_C(w)`.

`S^-` is guaranteed support: actions supported in every target world still
admitted by retained evidence. `S^+` is possible support: actions supported in at
least one such world.

This branch **does not** classify a recorded action as VALID, INVALID, or
UNRESOLVED; it does not choose regeneration; and it does not implement `R*`.
Those are subsequent semantic stages.

## Why production can compile from q artifacts without re-querying the target

Compiler v1 is deliberately deterministic. In every raw decision world,
projected current support is therefore a singleton `{z}`.

Every `q_{C,h}` layer refines `q_{C,0}`, and `q_{C,0}` groups worlds exactly by
current claim-projected output. Hence all worlds inside one valid q block have the
same singleton current support. Therefore replacing raw `Omega(e)` by its q image
preserves the support envelope exactly:

`intersection_{w in Omega(e)} S_C(w)`

`  = intersection_{q in q[Omega(e)]} S_C(q)`

and likewise for union.

Production checks this support-constancy invariant block by block rather than
assuming it. This is the bridge that lets the offline pipeline proceed from the
sealed quotient/evidence-image artifacts without consulting target execution
again.

## Production artifact

`replaymark.support_envelope.compile_support_envelope` consumes:

- a `BoundedQuotient`; and
- a `QEvidenceImage` sealed to that exact quotient and claim.

It records:

- quotient, claim, evidence, and evidence-image fingerprints;
- the q depth used;
- the current projected support attached to every q block; and
- for every evidence token, exact guaranteed and possible support.

The compiler fails closed if the evidence image belongs to another quotient,
references an unknown q block, or a q block does not preserve deterministic
current projected support.

Canonical action ordering is JSON-byte based rather than Python tuple ordering,
so mixed admitted scalar types cannot introduce an incidental comparison error.

## Independent definition oracle

`replaymark_oracle.support_envelope_oracle` does not import the production q,
evidence-image, or support-envelope compilers.

For each raw world `w in Omega(e)` it directly calls
`TargetModel.current_distribution(w)`, projects every positive-mass action through
`ClaimSpec`, obtains literal `S_C(w)`, and then computes set intersection/union.

Because support depends only on positive probability rather than deterministic
selection, this oracle also evaluates finite stochastic current decisions. That
is intentional: the production pipeline remains deterministic because the
bounded q compiler has not yet proved stochastic finite-horizon equivalence, but
the support theorem itself is not artificially weakened by that engineering
boundary.

## Canonical boundary cases

The frozen Better Thermostat model exposes an important separation between
predictive ambiguity and current support ambiguity.

For the N2b pair, the q evidence image grows from one predictive class at `H=0`
to two at `H=1`, yet both worlds currently emit `SET_AWAY`. Therefore:

`|q_{C,h}[Omega(e)]| : 1 -> 2 -> 2`

while at every tested depth:

`S^- = S^+ = {SET_AWAY}`.

This is exactly the distinction ReplayMark needs: future predictive state may
require more information even when the current historical action remains
support-certifiable.

Conversely, evidence admitting both a non-target `SET_HOME` world and an
at-target `NO_ACTION` world yields:

`S^- = empty`

`S^+ = {NO_ACTION, SET_HOME}`.

Stronger evidence selecting the non-target world expands guaranteed support to
`{SET_HOME}` and shrinks possible support to the same singleton, instantiating the
support-envelope monotonicity theorem.

A separate stochastic oracle fixture uses two compatible worlds with supports
`{A,B}` and `{B,C}` and obtains exactly:

`S^- = {B}`

`S^+ = {A,B,C}`.

## Verification

The branch requires all prior q/evidence-image gates to remain green, plus:

1. production-vs-raw-definition agreement for the Better Thermostat fixtures at
   q depths 0, 1, and 2;
2. N2b q-image refinement `1 -> 2 -> 2` while its support envelope stays the
   exact singleton `{SET_AWAY}`;
3. compression of multiple overwritten raw preset identities into
   `S^- = S^+ = {SET_HOME}`;
4. a genuine disagreement case with empty guaranteed support and two-element
   possible support;
5. stronger-evidence monotonicity;
6. stochastic definition-oracle overlap `{A,B}` / `{B,C}`;
7. hard binding between support artifact and its exact quotient/evidence image;
8. canonical recompilation stability; and
9. exhaustive deterministic differential verification over all 5,832 complete
   3-state / 2-continuation / 2-output machines at H=2 and all seven nonempty
   evidence subsets: **40,824** production-vs-definition envelopes, plus every
   strict evidence-refinement relation among those subsets.

## Next boundary

Only after this support-envelope stage is frozen should the next branch map a
**recorded projected action** `z` against the already-computed envelope:

- `z in S^-`;
- `z notin S^+`; or
- `z in S^+ \\ S^-`.

That next stage may realize `VALID / INVALID / UNRESOLVED`, but it must have its
own independent adjudication oracle. Maximal reuse policy `R*` remains one step
later still.
