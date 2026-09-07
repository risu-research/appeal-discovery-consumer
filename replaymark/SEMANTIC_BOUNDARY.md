# ReplayMark semantic boundary — support-envelope freeze

**Status:** bounded `q_{C,H}` compilation and q evidence-image compilation are frozen; exact deterministic `S_C^-(e)` / `S_C^+(e)` support-envelope compilation is implemented with an independent raw-definition oracle.  
**Original seed authority:** `replaymark-compiler-contract-seed@6da24cce48d1c2f6fe4bfabf4e01047e79b7e6eb`.  
**Bounded-q authority:** `replaymark-bounded-q-compiler@b2b357ce009d26e56e4422a3d61aade57ca6064a`.  
**Evidence-image authority:** `replaymark-q-evidence-image@f43c0c69b2eb8e62b762fec939386e82cc521b8a`.  
**Current scope:** public semantic types, two-phase target semantics, bounded deterministic `q_{C,H}`, independent q oracle, extensional `q_{C,H}[Omega(e)]`, independent evidence-image oracle, and exact deterministic support envelopes.  
**Still out of scope:** recorded-action adjudication, `VALID / INVALID / UNRESOLVED`, `CompiledContract` realization, maximal reuse guard `R*`, runtime gate insertion, replay/regeneration policy integration, BDD/bitset optimization, stochastic q compilation, and new live experiments.

## 1. Public semantic boundary remains small

The package root continues to export exactly six semantic types:

1. `ClaimSpec`
2. `TargetModel`
3. `EvidenceSpec`
4. `ProjectedAction`
5. `CompiledContract`
6. `Verdict`

Compiler stages, storage representations, runtime gates, substrate adapters, and
verification oracles remain explicit submodules rather than public semantic
types.

The Replay-Sufficiency Factorization is now executable through:

`claim -> projected actions -> q_{C,H} -> evidence image -> support envelope`

but **not yet** through adjudication or maximal certified reuse.

## 2. Claim/action semantics

`ClaimSpec` is normative: stable claim identity, exact consequential dimensions,
claim-bound non-negative horizon, and consequence endpoint. Missing adapter
coordinates fail closed rather than being guessed.

`ProjectedAction` remains immutable and substrate-neutral. Home Assistant, MQTT,
and thermostat vocabulary lives only in adapters/fixtures, not ReplayMark core.

## 3. Two-phase `TargetModel`

One predictive step remains:

```text
decision_state
    -- current_distribution --> (current action, post-decision state)
post-decision state
    -- advance_distribution(future continuation) --> next decision_state
```

This keeps current target evidence separate from future admitted continuation.
Exact rational probabilities remain representable at the protocol boundary, but
the production bounded-q compiler accepts only deterministic point masses until a
stochastic finite-horizon compiler is independently proved.

## 4. Bounded `q_{C,H}`

Production computes exactly:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for every admitted u)`.

Only `0..H` are computed; no hidden `H+1` convergence probe is allowed.
`agentmark.minimize.quotient()` remains historical algorithmic precedent only,
never ReplayMark `q_{C,H}`.

The independent q oracle enumerates continuation words and exact projected
output-trace laws rather than reusing production refinement.

## 5. Evidence semantics and evidence image

Each `EvidenceSpec` token denotes exactly the nonempty finite set `Omega(e)` of
target decision states/histories still compatible with retained evidence.

The q evidence image is:

`I_{C,h}(e) := q_{C,h}[Omega(e)]`.

Production maps each raw compatible state into an already-computed q block and
seals the result to quotient, claim, evidence, and q depth. Unknown target states
or deeper uncompiled layers fail closed.

The evidence-image oracle derives q from the independent definition oracle and
then takes the literal set image of `Omega(e)`. It does not import production q
or evidence-image code.

## 6. New stage: support envelope

For every raw compatible world `w`, let `S_C(w)` be the positive support of its
current `ClaimSpec`-projected target decision. Define:

`S_C^-(e) := intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) := union_{w in Omega(e)} S_C(w)`.

`S^-` is guaranteed support; `S^+` is possible support.

The current branch compiles exactly these two sets. It does **not** inspect a
recorded action `z` and therefore does not produce a replay verdict.

## 7. Quotient-preservation bridge

The production bounded-q pipeline is deterministic. Each raw world therefore has
singleton current projected support `{z}`. Every q layer refines `q_{C,0}`, and
`q_{C,0}` groups worlds by exactly that current projected action.

Therefore support is constant within every valid q block and:

`intersection_{w in Omega(e)} S_C(w)`

`= intersection_{q in q[Omega(e)]} S_C(q)`

with the analogous equality for union.

Production derives one explicit support entry per q block and checks that all
block members really share the same current projected action. A violation fails
closed. This prevents an implementation shortcut from silently using q block IDs
without proving that the support semantics survived quotienting.

## 8. Support-envelope artifact binding

`replaymark/support_envelope.py` consumes only:

- a sealed `BoundedQuotient`; and
- a `QEvidenceImage` compiled from that exact quotient.

It records quotient, claim, evidence, and evidence-image fingerprints; q depth;
block-level projected supports; and token-level guaranteed/possible support.

A foreign evidence image, unknown q block, malformed current-action table, or q
block whose members disagree on current projected support is rejected.

No `VALID`, `INVALID`, `UNRESOLVED`, regeneration, or reuse method is exposed.

## 9. Independent support definition oracle

`replaymark_oracle/support_envelope_oracle.py` bypasses production q,
evidence-image, and support-envelope code.

For each raw `w in Omega(e)` it directly evaluates
`TargetModel.current_distribution(w)`, retains only positive probability mass,
projects each action through `ClaimSpec`, forms literal `S_C(w)`, and computes
intersection/union.

Because this definition depends only on support, not deterministic selection, the
oracle can evaluate finite stochastic current decisions even though the current
production q pipeline cannot. This preserves the theory's actual scope while
keeping production claims narrower and proved.

## 10. Canonical separating examples

The Better Thermostat N2b pair demonstrates that predictive ambiguity and current
support ambiguity are not the same thing:

- q evidence-image cardinality: `1 -> 2 -> 2` for depths 0, 1, 2;
- support envelope at all three depths: `S^- = S^+ = {SET_AWAY}`.

Thus a longer consequence horizon can require more predictive target information
while still leaving the current historical action support-certifiable.

A second thermostat evidence set admitting one non-target `SET_HOME` world and
one at-target `NO_ACTION` world yields:

- `S^- = empty`;
- `S^+ = {NO_ACTION, SET_HOME}`.

Stronger evidence selecting the non-target world yields the exact singleton
`S^- = S^+ = {SET_HOME}`.

The stochastic definition-only fixture uses supports `{A,B}` and `{B,C}` and
returns exactly `S^-={B}`, `S^+={A,B,C}`.

## 11. Verification independence wall

The layers remain deliberately distinct:

- production bounded q: `replaymark/q_compiler.py`;
- q definition oracle: `replaymark_oracle/definition_q_oracle.py`;
- production evidence image: `replaymark/evidence_image.py`;
- evidence-image oracle: `replaymark_oracle/evidence_image_oracle.py`;
- production support envelope: `replaymark/support_envelope.py`;
- raw-definition support oracle: `replaymark_oracle/support_envelope_oracle.py`;
- historical/live scientific validators remain outside production.

Production support code does not import any oracle. The support oracle does not
import production q/evidence/support compilers.

## 12. Admitted verification

This branch is closed only if all prior gates remain green and the new gate also
passes:

- production-vs-raw-definition agreement for thermostat support envelopes at q
  depths 0, 1, 2;
- exact N2b `1 -> 2 -> 2` predictive-image refinement with invariant singleton
  current support;
- exact overwritten-preset compression and at-target disagreement cases;
- support-envelope monotonicity under stronger evidence;
- stochastic `{A,B}` / `{B,C}` oracle overlap;
- hard fingerprint binding between quotient and evidence image;
- canonical recompilation stability;
- exhaustive deterministic differential verification across all **5,832**
  complete 3-state / 2-continuation / 2-output machines at H=2 and all seven
  nonempty evidence subsets, for **40,824** production-vs-definition envelopes;
- every strict nonempty evidence-refinement relation among those subsets,
  totaling **69,984** monotonicity checks.

## 13. Next boundary, not crossed here

Only after this support-envelope stage is frozen may a later branch take a
recorded projected action `z` and implement the exact trichotomy:

- `z in S^-`;
- `z notin S^+`;
- `z in S^+ \\ S^-`.

That is the natural `VALID / INVALID / UNRESOLVED` adjudication layer, but it must
have its own independent oracle. The maximally permissive reuse rule `R*` remains
one further step after adjudication rather than being smuggled into this branch.
