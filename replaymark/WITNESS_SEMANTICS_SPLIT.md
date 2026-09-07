# ReplayMark witness-semantics split and production predictive witnesses

## 1. Why the old generic word `witness` is unsafe

ReplayMark now has two constructive explanations with different domains and
proof obligations. Treating them as one API would blur the difference between
claim-predictive inequivalence and historical-reuse unsoundness.

### Predictive continuation witness

Given two target decision worlds `w1,w2`, a predictive witness is a shortest
admitted continuation word `u` such that their claim-projected output traces
differ under `u`.

It answers:

> Why are these two target worlds in different `q_{C,H}` classes?

It depends on:

- target semantics;
- claim projection;
- continuation alphabet; and
- bounded horizon.

It does **not** depend on retained evidence, an observation token, a recorded
historical action, `S-/S+`, adjudication, or R*.

### R* reuse counterexample world

For fixed evidence `e` and recorded projected action `z`, an R* counterexample is
one raw compatible target world `w in Omega(e)` in which `z` is not positively
supported.

It answers:

> Why would reusing this historical action under this evidence be unsound?

It depends on `e` and `z`. It is a raw world, not a continuation sequence. There
is no shortest-continuation semantics attached to it.

These objects can coexist for the same system but prove different facts.

## 2. Production predictive-witness semantics

For deterministic bounded `q_{C,H}`, define a continuation word `u` to separate
worlds `s,t` iff the claim-projected output traces generated from `s` and `t`
under `u` differ.

A production `PredictiveContinuationWitness` stores:

- the canonical unordered pair of decision worlds;
- the selected already-compiled q depth;
- the shortest continuation word;
- its first q-separation depth;
- both resulting projected output traces;
- the quotient fingerprint; and
- the claim fingerprint.

Length zero is admitted and meaningful: if current projected outputs already
differ, the empty word is the shortest witness.

For equal-length shortest words, ReplayMark uses the TargetModel's declared
continuation order as the deterministic canonical tie break. Reordering the
alphabet may therefore change which equally short witness is serialized, but it
must not change the q equivalence relation or the minimum witness length.

## 3. Why shortestness falls directly out of bounded refinement

The bounded quotient is defined by all continuation words of length at most `h`.
Therefore:

- if a pair is equivalent in `q_{C,h-1}`, **no** word of length `<= h-1`
  distinguishes it;
- if the same pair separates in `q_{C,h}`, at least one continuation leads to a
  successor pair already separated by `q_{C,h-1}`.

Thus the first layer `d` at which a pair separates is exactly the length of its
shortest distinguishing continuation.

Production synthesis exploits this as a backpointer recurrence:

- depth 0: different current projected outputs -> empty word;
- depth `d>0`: prepend one splitting continuation to an already-shortest witness
  of the corresponding successor pair from an earlier layer.

No target-model exploration is repeated. `replaymark.predictive_witness` consumes
only the sealed `BoundedQuotient` artifact: its q layers, current projected
actions, deterministic successor table, and declared continuation order.

This is preferable to calling the slow definition oracle at runtime or separately
breadth-first searching the original target model. The q compiler has already
computed precisely the information needed to justify minimal separation.

## 4. Production artifact and fail-closed checks

`PredictiveWitnessIndex` contains one shortest certificate for every unordered
state pair separated by the selected q layer, and no certificate for pairs still
equivalent at that depth.

Before synthesis the production compiler checks that:

- q layers form monotone refinements;
- current projected actions cover the entire decision-world domain;
- deterministic successor rows cover the entire world domain;
- every required continuation is present exactly once;
- successor worlds remain inside the declared q domain; and
- q0 agrees exactly with current projected-action equality.

During synthesis it rejects:

- a pair separated by q without a valid splitter/backpointer;
- a backpointer whose successor pair lacks an earlier witness;
- a first-separation depth inconsistent with witness length;
- a reconstructed word whose two projected traces are actually equal; and
- any attempt to request an uncompiled deeper horizon.

The resulting certificate stores both traces, so the claimed separation remains
auditable without re-running the target adapter.

## 5. Independent definition oracle

The existing `replaymark_oracle.definition_q_oracle.shortest_distinguishing_word`
remains the independent definition-level authority. It does not consume the
production witness index or bounded-refinement backpointers. Instead it enumerates
continuation words by increasing length and directly evaluates exact projected
output-trace laws.

For deterministic targets, the production witness must exactly equal the first
word returned by that oracle under the declared continuation order.

The two implementations therefore differ materially:

- production: dynamic backpointers over already-compiled q refinement;
- oracle: literal word enumeration plus trace-law evaluation.

They share only the semantic contracts/target model as the intentional TCB.

## 6. Canonical Better Thermostat witnesses

The production compiler must reproduce the two already-frozen scientific
examples:

- N2b pair: shortest witness `presence_toggle`, first separation depth 1;
- depth-2 pair: shortest witness `presence_toggle -> night_toggle`, first
  separation depth 2.

The former distinguishes `SET_HOME` from `SET_COMFORT` one decision later. The
latter remains equal for the first continuation and separates only after the
second.

A pair whose current claim-projected actions differ must produce the empty word
at depth 0.

## 7. Explicit separation from R* counterexamples

No production predictive-witness object contains:

- evidence observation;
- historical recorded action;
- support envelope;
- adjudication verdict;
- reuse disposition; or
- R* counterexample world.

Conversely, the R* definition oracle's maximality counterexample is a single raw
compatible world excluding `z`; it has no `continuation_word` and no shortestness
claim.

The early seed `CompiledContract.shortest_witness(observation, historical_action)`
therefore conflates two semantics and **must not be implemented as written**. It
remains only a provisional seed interface until the later CompiledContract API
re-freeze. The final contract should expose predictive continuation witnesses and
reuse counterexample worlds through distinct operations.

## 8. Verification gate

This increment is closed only if:

1. production reproduces the canonical N2b depth-1 and thermostat depth-2 words;
2. current-output differences produce a valid empty-word certificate;
3. reversed pair lookup returns the same canonical unordered-pair certificate;
4. an equal-length tie fixture selects the first continuation in the declared
   alphabet order, while reversing that order changes only the canonical witness
   choice and not q inequivalence or minimum length;
5. malformed successor artifacts, unknown worlds, and uncompiled deeper horizons
   fail closed;
6. the predictive-witness object and R* raw counterexample are structurally
   distinct;
7. for **all 5,832** complete 3-state / 2-continuation / 2-output deterministic
   machines, every one of the three unordered state pairs is checked at depths
   0,1,2,3: **69,984 production-vs-definition witness queries**;
8. every produced witness exactly matches the independent oracle word;
9. every produced witness's first-separation depth equals its word length and all
   shallower q layers still merge that pair;
10. every stored left/right trace exactly matches independent trace-law
    evaluation and genuinely differs; and
11. lookup symmetry is checked on all 69,984 pair-depth queries.

All prior semantic gates are rerun in the same workflow.

## 9. Scope discipline

This branch does not:

- alter q equivalence semantics;
- change evidence closure, support, adjudication, or R*;
- add runtime fallback policy;
- implement the final CompiledContract;
- add compiler-observed full target provenance; or
- run a live E3b intervention.

The next pre-packaging hardening item remains compiler-observed target-semantic
provenance, followed by the CompiledContract API re-freeze.
