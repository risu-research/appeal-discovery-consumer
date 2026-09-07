# ReplayMark semantic boundary — maximal certified reuse freeze

**Status:** bounded `q_{C,H}`, q evidence image, deterministic support envelope,
three-valued adjudication, and theorem-induced maximal certified reuse `R*` are
implemented with independent definition oracles.  
**Original seed authority:** `replaymark-compiler-contract-seed@6da24cce48d1c2f6fe4bfabf4e01047e79b7e6eb`.  
**Bounded-q authority:** `replaymark-bounded-q-compiler@b2b357ce009d26e56e4422a3d61aade57ca6064a`.  
**Evidence-image authority:** `replaymark-q-evidence-image@f43c0c69b2eb8e62b762fec939386e82cc521b8a`.  
**Support-envelope authority:** `replaymark-support-envelope@c74929bf0a75a8a920fe951a18b694d82fc32e73`.  
**Adjudication authority:** `replaymark-three-valued-adjudicator@4e6d70894a7ba5af2206d8ddcf0c5842ad0be658`.  
**Current scope:** semantic types, deterministic bounded predictive state,
`q[Omega(e)]`, exact `S^- / S^+`, `VALID / INVALID / UNRESOLVED`, and fixed-evidence
maximal certified historical reuse.  
**Still out of scope:** concrete `CompiledContract` realization, target-native
fallback selection, evidence-acquisition policy, runtime gate insertion,
replay/regeneration integration, cost optimization, BDD/bitset optimization,
stochastic q compilation, and new live experiments.

## 1. Public semantic boundary remains deliberately small

The package root still exports exactly six semantic types:

1. `ClaimSpec`
2. `TargetModel`
3. `EvidenceSpec`
4. `ProjectedAction`
5. `CompiledContract`
6. `Verdict`

Compiler stages, adjudicators, reuse dispositions, storage representations,
adapters, and oracles remain explicit submodules rather than additional root
semantic types.

The executable Replay-Sufficiency Factorization now reaches:

`claim -> projected actions -> q_{C,H} -> evidence image -> support envelope -> adjudication -> maximal certified reuse`

but does **not** yet instantiate a runtime `CompiledContract` or choose a fallback
execution action.

## 2. Claim and action semantics

`ClaimSpec` remains normative: stable claim identity, exact consequential action
dimensions, claim-bound horizon, and consequence endpoint. Missing dimensions
fail closed.

Recorded actions may contain additional adapter coordinates. Adjudication applies
the exact claim projection before support membership is tested, so irrelevant
coordinates cannot alter the scientific identity of the historical consequence.

## 3. Two-phase target semantics

One predictive step remains:

```text
decision_state
    -- current_distribution --> (current action, post-decision state)
post-decision state
    -- advance_distribution(future continuation) --> next decision_state
```

Current target evidence is therefore not conflated with future admitted
continuation. Exact rational probabilities remain representable at the
`TargetModel` boundary. Production bounded-q compilation remains deterministic
until a stochastic q compiler is separately proved.

## 4. Bounded `q_{C,H}`

Production computes exactly:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for every admitted u)`.

Only `0..H` are compiled. No hidden `H+1` convergence probe is admitted. The
independent q oracle enumerates continuation words and exact projected
output-trace laws rather than reusing production refinement.

## 5. Evidence image

Every evidence token denotes a nonempty finite compatible-world set `Omega(e)`.
The evidence image is:

`I_{C,h}(e) := q_{C,h}[Omega(e)]`.

Production maps raw compatible worlds into an already-compiled q layer and seals
the result to quotient, claim, evidence, and depth. The independent oracle derives
q from the continuation-word definition and then takes the literal set image.

## 6. Support envelope

For each raw compatible world `w`, let `S_C(w)` be positive current projected
support. Define:

`S_C^-(e) := intersection_{w in Omega(e)} S_C(w)`

`S_C^+(e) := union_{w in Omega(e)} S_C(w)`.

`S^-` is guaranteed support and `S^+` is possible support.

Deterministic q layers refine `q_{C,0}`, so current support is constant inside each
valid q block. Production checks that invariant and compiles exact envelopes from
sealed q/evidence artifacts. The independent support oracle bypasses all such
intermediate artifacts and computes intersection/union directly over raw worlds.

## 7. Three-valued adjudication

For recorded claim-projected action `z`:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` iff `z in S_C^+(e) \\ S_C^-(e)`.

These cases are mutually exclusive and exhaustive. `UNRESOLVED` is semantic
underdetermination under current evidence, not a confidence score or an error.

The adjudicator returns a sealed `Adjudication` certificate and does not choose
reuse, regeneration, evidence acquisition, or abort.

## 8. New stage: theorem-induced `R*`

A fixed-evidence binary reuse rule sees the already-established semantic pair
`(e,z)` and chooses only:

- `REUSE`; or
- `DO_NOT_REUSE`.

Such a rule is support-sound when every REUSE choice is supported in every target
world still compatible with `e`.

Define:

`R*(e,z) = REUSE iff z in S_C^-(e)`.

Equivalently in terms of frozen adjudication:

- `VALID -> REUSE`;
- `INVALID -> DO_NOT_REUSE`;
- `UNRESOLVED -> DO_NOT_REUSE`.

This is not an arbitrary policy convention. Under the pointwise order
`DO_NOT_REUSE < REUSE`, R* selects the greatest support-sound choice at every
fixed-evidence pair. Any attempted additional reuse has at least one compatible
raw target world that excludes `z`.

## 9. Theorem versus policy hard wall

The R* theorem establishes only historical reuse entitlement.

`DO_NOT_REUSE` does **not** specify what execution should happen next.

The following remain outside the theorem and outside this branch:

- target-native regeneration;
- stronger-evidence acquisition;
- evidence ordering;
- abort/fallback behavior;
- cost/latency/energy optimization; and
- stochastic distributional fidelity.

INVALID and UNRESOLVED both map to DO_NOT_REUSE because neither certifies
historical reuse. The `RStarDecision` nevertheless preserves the original verdict
so a future execution layer can distinguish their reasons without changing R*.

## 10. Production R* artifact

`replaymark/rstar.py` consumes one sealed `Adjudication` and returns an immutable
`RStarDecision` containing:

- adjudication fingerprint;
- support-envelope fingerprint;
- claim and evidence fingerprints;
- q depth;
- evidence token;
- exact projected recorded action;
- original three-valued verdict; and
- binary `ReuseDisposition`.

The certificate validates its own theorem truth table. Its binary domain contains
only `REUSE` and `DO_NOT_REUSE`; it exposes no regeneration, evidence-refinement,
or abort operation.

## 11. Completely independent R* oracle

`replaymark_oracle/rstar_oracle.py` imports none of the production q,
evidence-image, support-envelope, adjudicator, or R* modules.

For every raw `w in Omega(e)` it directly evaluates current target semantics,
keeps positive-mass target actions, applies the claim projection, and checks
whether `z` is supported.

- if no compatible world excludes `z`, the oracle returns REUSE;
- otherwise it returns DO_NOT_REUSE and records at least one excluding raw world.

That excluding world is a constructive maximality witness: any fixed-evidence
policy that reused at the same pair would be support-unsound.

The oracle admits finite stochastic current supports. Production remains bounded
by deterministic q compilation.

## 12. Canonical separating examples

The Better Thermostat N2b pair has q evidence-image cardinality `1 -> 2 -> 2` for
H=0,1,2 while both compatible worlds support `SET_AWAY`. Adjudication remains
VALID and R* remains REUSE at every depth.

Evidence mixing one `SET_HOME` world and one at-target `NO_ACTION` world makes
recorded `SET_HOME` and `NO_ACTION` UNRESOLVED and recorded `SET_AWAY` INVALID.
R* returns DO_NOT_REUSE for all three while preserving the distinct underlying
verdicts.

Stronger evidence selecting only the `SET_HOME` world makes recorded `SET_HOME`
VALID and therefore REUSE-certified.

An oracle-only stochastic fixture with supports `{A,B}` and `{B,C}` gives
`B -> REUSE`, `A -> DO_NOT_REUSE`, and zero-mass `ZERO -> DO_NOT_REUSE`.

## 13. Verification independence wall

The layers remain intentionally distinct:

- production q: `replaymark/q_compiler.py`;
- q oracle: `replaymark_oracle/definition_q_oracle.py`;
- production evidence image: `replaymark/evidence_image.py`;
- evidence-image oracle: `replaymark_oracle/evidence_image_oracle.py`;
- production support envelope: `replaymark/support_envelope.py`;
- raw support oracle: `replaymark_oracle/support_envelope_oracle.py`;
- production adjudicator: `replaymark/adjudicator.py`;
- raw adjudication oracle: `replaymark_oracle/adjudication_oracle.py`;
- production R*: `replaymark/rstar.py`;
- raw R* oracle: `replaymark_oracle/rstar_oracle.py`.

Production R* consumes only a sealed adjudication. The R* oracle imports only the
public semantic contracts and directly queries raw target semantics.

## 14. Admitted verification

This branch is closed only if every prior semantic gate remains green and R* also
passes:

- production-vs-raw-oracle agreement on canonical thermostat reuse/non-reuse
  cases;
- N2b REUSE persistence across predictive-image refinement `1 -> 2 -> 2`;
- INVALID and UNRESOLVED both mapping to DO_NOT_REUSE while remaining distinct
  certificate facts;
- stronger-evidence transition into certified REUSE;
- projection invariance to non-claim recorded coordinates;
- no fallback-policy surface in the binary R* artifact;
- rejection of theorem-inconsistent forged R* certificates;
- stochastic raw-definition support tests including zero mass;
- exhaustive differential verification across all **5,832** complete 3-state /
  2-continuation / 2-output deterministic machines at H=2, all seven nonempty
  evidence subsets, and both recorded actions: **81,648** exact R* decisions;
- a raw excluding-world counterexample for every exhaustive DO_NOT_REUSE pair;
- pointwise maximality at every exhaustive pair; and
- every strict evidence-refinement relation for both recorded actions, totaling
  **139,968** certified-reuse persistence checks.

The expected exhaustive split is REUSE `27,702` and DO_NOT_REUSE `53,946`.

## 15. Next boundary, deliberately not crossed here

Only after R* is frozen may a later branch realize the concrete `CompiledContract`
that packages the already-verified semantic artifacts for cheap runtime lookup.

That later contract must remain observationally equivalent to the semantic chain
frozen here. Runtime fallback policy and live E3b intervention remain subsequent
steps rather than being smuggled into maximal certified reuse.
