# ReplayMark `q_{C,H}` evidence image

## Scope

This increment implements exactly one new arrow in the Replay-Sufficiency
Factorization:

`q_{C,H} + EvidenceSpec -> q_{C,H}[Omega(e)]`.

For an evidence token `e`, `EvidenceSpec` already defines the nonempty finite set
`Omega(e)` of target decision states/histories still compatible with retained
evidence. The evidence image is the set of bounded claim-predictive classes those
worlds can occupy:

`I_{C,H}(e) := { q_{C,H}(w) : w in Omega(e) }`.

This is not yet a support envelope. No `S^-`, `S^+`, three-valued verdict,
regeneration decision, reuse guard, or runtime policy is implemented here.

## Why this is a separate compiler stage

Raw evidence ambiguity and claim-relevant ambiguity are different objects.
Multiple raw target histories can remain compatible with the same evidence while
all belonging to one `q_{C,H}` class. Conversely, a raw evidence set that is
harmless at `H=0` can cross multiple predictive classes when the benchmark
endpoint extends forward.

Keeping this image explicit prevents later support/adjudication code from
silently reconstructing full target state or, in the opposite direction, from
discarding distinctions that `q_{C,H}` proved consequential.

## Production semantics

`replaymark.evidence_image.compile_evidence_image` accepts only:

- an already-compiled `BoundedQuotient`;
- an extensional `EvidenceSpec`; and
- optionally an already-computed layer `0 <= h <= H`.

For every evidence token it validates that all compatible worlds are inside the
compiled target domain and returns the canonical set of q-block IDs touched by
those worlds. Unknown target states fail closed. A request for `H+1` fails rather
than triggering hidden lookahead.

The artifact is sealed by the quotient, claim, and evidence fingerprints and by
canonical bytes. It does not expose any verdict method.

## Independent definition oracle

`replaymark_oracle.evidence_image_oracle` does not import the production evidence
image or the production q compiler. It first obtains the mathematical
`q_{C,h}` partition from the existing continuation-word/output-trace definition
oracle and then takes the literal set image of `Omega(e)`.

Verification compares semantic block member sets rather than production block
labels.

## High-value boundary cases

The frozen Better Thermostat model gives both directions needed for this stage.

- The N2b pair occupies one evidence-image class at `H=0` but two at `H=1`.
  Thus evidence adequacy can be consequence-horizon relative even when the
  current action agrees.
- Three distinct non-target current presets under the same feedback vector map
  to one stable predictive class because the current decision overwrites their
  exact identity. Thus raw-world multiplicity need not imply claim-relevant
  ambiguity.
- Adding the at-target world restores two predictive classes, showing that the
  image preserves the one preset bit the stable q relation actually needs.

## Verification

The gate requires:

1. production-vs-definition agreement for all Better Thermostat fixture tokens
   at depths 0, 1, and 2;
2. the exact N2b image refinement `1 -> 2 -> 2`;
3. stable compression of three overwritten non-target worlds to one q class;
4. separation when an at-target world is added;
5. subset monotonicity under stronger extensional evidence;
6. canonical invariance to evidence token/state input order;
7. fail-closed behavior for evidence outside the q domain;
8. no hidden deeper q layer; and
9. exhaustive H=0 set-image agreement across all 27 three-state assignments of
   three output labels and all seven nonempty evidence subsets, exercising all
   five possible set-partition relations on a three-element domain.

## Next boundary

Only after this evidence-image stage is frozen should a later branch implement
the support envelope `S_C^-(e), S_C^+(e)`. That branch must have its own
independent definition oracle. Three-valued adjudication and maximal reuse remain
subsequent steps rather than being bundled into the support-envelope compiler.
