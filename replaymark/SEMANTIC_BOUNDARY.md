# ReplayMark semantic boundary — three-valued adjudication freeze

**Status:** bounded `q_{C,H}`, q evidence image, deterministic support envelope,
and exact three-valued support adjudication are implemented with independent
definition oracles.  
**Original seed authority:** `replaymark-compiler-contract-seed@6da24cce48d1c2f6fe4bfabf4e01047e79b7e6eb`.  
**Bounded-q authority:** `replaymark-bounded-q-compiler@b2b357ce009d26e56e4422a3d61aade57ca6064a`.  
**Evidence-image authority:** `replaymark-q-evidence-image@f43c0c69b2eb8e62b762fec939386e82cc521b8a`.  
**Support-envelope authority:** `replaymark-support-envelope@c74929bf0a75a8a920fe951a18b694d82fc32e73`.  
**Current scope:** semantic types, deterministic bounded predictive state,
`q[Omega(e)]`, exact `S^- / S^+`, and `VALID / INVALID / UNRESOLVED` for one
recorded claim-projected action.  
**Still out of scope:** maximal reuse policy `R*`, `CompiledContract` concrete
realization, runtime gate insertion, replay/regeneration policy integration,
BDD/bitset optimization, stochastic q compilation, and new live experiments.

## 1. Public semantic boundary remains deliberately small

The package root still exports exactly six semantic types:

1. `ClaimSpec`
2. `TargetModel`
3. `EvidenceSpec`
4. `ProjectedAction`
5. `CompiledContract`
6. `Verdict`

Compiler stages, adjudicators, storage representations, adapters, and oracles are
explicit submodules rather than additional root semantic types.

The executable Replay-Sufficiency Factorization now reaches:

`claim -> projected actions -> q_{C,H} -> evidence image -> support envelope -> three-valued adjudication`

but does **not** yet reach maximal certified reuse.

## 2. Claim and recorded-action semantics

`ClaimSpec` is normative: stable claim identity, exact consequential dimensions,
claim-bound horizon, and consequence endpoint. Missing dimensions fail closed.

A recorded `ProjectedAction` may carry more adapter coordinates than the claim.
Adjudication applies the exact sealed `ClaimSpec` before support membership is
tested, so non-consequential coordinates cannot alter the scientific verdict.

## 3. Two-phase target semantics

One prediction step remains:

```text
decision_state
    -- current_distribution --> (current action, post-decision state)
post-decision state
    -- advance_distribution(future continuation) --> next decision_state
```

This prevents current evidence and future continuation from being conflated.
Exact rational probabilities remain representable in `TargetModel`; production
bounded-q compilation remains deterministic until a stochastic q compiler is
separately proved.

## 4. Bounded `q_{C,H}`

Production computes exactly:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for every admitted u)`.

Only layers `0..H` are computed. No hidden `H+1` convergence probe is permitted.
The independent definition oracle enumerates continuation words and exact
projected output-trace laws instead of reusing production refinement.

## 5. Evidence image

Every `EvidenceSpec` token denotes the nonempty finite compatible-world set
`Omega(e)`. The evidence image is:

`I_{C,h}(e) := q_{C,h}[Omega(e)]`.

Production maps raw compatible worlds to already-computed q blocks and binds the
artifact to quotient, claim, evidence, and depth. The independent oracle derives
the q relation from the continuation-word definition and then takes the literal
set image.

## 6. Support envelope

For raw compatible world `w`, let `S_C(w)` be its positive current projected
support. The exact envelope is:

`S_C^-(e) := intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) := union_{w in Omega(e)} S_C(w)`.

`S^-` is guaranteed support and `S^+` is possible support.

Because deterministic q layers refine `q_{C,0}`, current support is constant
inside every valid q block. Production checks this invariant and can therefore
compile exact envelopes from the sealed q/evidence artifacts without re-querying
the target. The independent support oracle bypasses production q/evidence/support
code and computes intersection/union directly over raw target worlds.

## 7. New stage: exact three-valued adjudication

Given recorded claim-projected action `z`, the adjudicator implements exactly:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` iff `z in S_C^+(e) \\ S_C^-(e)`.

These cases are mutually exclusive and exhaustive because `S^- subseteq S^+`.

`UNRESOLVED` means semantic underdetermination under the current evidence. It is
not an error, confidence level, or probabilistic guess.

The adjudicator does not choose reuse or regeneration. Verdict and execution
policy remain separate objects.

## 8. Production adjudication artifact

`replaymark/adjudicator.py` consumes:

- a sealed `SupportEnvelope`;
- the exact `ClaimSpec` matching the envelope fingerprint;
- one evidence token; and
- one recorded `ProjectedAction`.

Before membership testing it checks:

- nonempty q image;
- nonempty `S^+`;
- no duplicate support actions;
- `S^- subseteq S^+`; and
- exact claim-dimensionality of every support action.

The returned immutable `Adjudication` records support-envelope, claim, and
evidence fingerprints; q depth; evidence token; projected recorded action;
membership in `S^-` and `S^+`; and the three-valued `Verdict`.

The dataclass validates its own membership/verdict truth table. No replay policy
method is exposed.

## 9. Completely independent adjudication oracle

`replaymark_oracle/adjudication_oracle.py` imports none of the production q,
evidence-image, support-envelope, or adjudicator modules.

It directly evaluates each raw `w in Omega(e)` using
`TargetModel.current_distribution(w)`, keeps positive-mass actions, applies the
claim projection, and records whether each compatible world supports `z`.

- all worlds support `z` -> `VALID`;
- no worlds support `z` -> `INVALID`;
- both supporting and excluding worlds exist -> `UNRESOLVED`.

The raw supporting/excluding world sets exist only as oracle diagnostics.
Production adjudication does not depend on them.

The oracle can evaluate finite stochastic current supports. Production remains
bounded by the deterministic q pipeline.

## 10. Canonical separating examples

The Better Thermostat N2b pair has predictive image cardinality `1 -> 2 -> 2`
for H=0,1,2, but both worlds currently support `SET_AWAY`; the recorded
`SET_AWAY` is therefore `VALID` at every tested depth.

Evidence mixing one `SET_HOME` world and one at-target `NO_ACTION` world gives
`S^- = empty`, `S^+ = {SET_HOME, NO_ACTION}`. Thus recorded `SET_HOME` and
`NO_ACTION` are both `UNRESOLVED`, while recorded `SET_AWAY` is `INVALID`.

Stronger evidence selecting only the `SET_HOME` world makes `SET_HOME` `VALID`
and `NO_ACTION` `INVALID`.

An oracle-only stochastic fixture with world supports `{A,B}` and `{B,C}` gives:
`B -> VALID`, `A -> UNRESOLVED`, and an explicit zero-mass action
`ZERO -> INVALID`.

## 11. Verification independence wall

The layers remain intentionally distinct:

- production q: `replaymark/q_compiler.py`;
- q oracle: `replaymark_oracle/definition_q_oracle.py`;
- production evidence image: `replaymark/evidence_image.py`;
- evidence-image oracle: `replaymark_oracle/evidence_image_oracle.py`;
- production support envelope: `replaymark/support_envelope.py`;
- raw support oracle: `replaymark_oracle/support_envelope_oracle.py`;
- production adjudicator: `replaymark/adjudicator.py`;
- raw adjudication oracle: `replaymark_oracle/adjudication_oracle.py`.

Production adjudication imports the support artifact but no oracle. The
adjudication oracle imports only the public semantic contracts and directly
queries raw target semantics.

## 12. Admitted verification

This branch is closed only if all previous gates remain green and the new gate
also passes:

- production-vs-raw-oracle agreement for thermostat VALID, INVALID, and
  UNRESOLVED cases;
- N2b `SET_AWAY` remaining VALID while predictive q image refines `1 -> 2 -> 2`;
- exact mixed-world UNRESOLVED and outside-`S^+` INVALID cases;
- stronger-evidence transition to exact VALID/INVALID outcomes;
- invariance to extra non-claim recorded-action coordinates;
- fail-closed foreign claim, missing required action dimensions, unknown evidence
  token, and malformed `S^- not subseteq S^+` artifact;
- stochastic oracle trichotomy with zero-mass exclusion; and
- exhaustive differential verification over all **5,832** complete
  3-state / 2-continuation / 2-output deterministic machines at H=2, all seven
  nonempty evidence subsets, and both recorded output actions: **81,648** exact
  production-vs-definition adjudications, with all three verdicts required to
  occur.

## 13. Next boundary, deliberately not crossed here

Only after adjudication is frozen may a later branch implement the theorem-induced
maximal certified reuse rule `R*`.

That next stage may map semantic verdicts into execution choices, but it must not
retroactively alter the adjudication semantics frozen here. `CompiledContract`
realization and live E3b intervention remain later steps.
