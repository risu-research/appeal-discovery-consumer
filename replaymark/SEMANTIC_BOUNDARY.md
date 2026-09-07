# ReplayMark semantic boundary — predictive-witness freeze

**Status:** bounded `q_{C,H}`, compiler-owned evidence semantics, q evidence image,
deterministic support envelope, three-valued adjudication, theorem-induced
maximal certified reuse `R*`, and production shortest predictive-continuation
witnesses are implemented with independent definition checks.  
**Evidence-semantics authority:** `replaymark-evidence-semantics-closure@993ad4a8526542c96b1ab8084ce1796488446455`.  
**Current branch scope:** split predictive continuation witnesses from R* raw-world
counterexamples and synthesize shortest q-separation witnesses from the already
compiled refinement artifact.  
**Still out of scope:** concrete `CompiledContract`, compiler-observed full
target-semantic provenance digest, runtime raw-observation canonicalizer,
target-native fallback policy, runtime E3b gate, stochastic q compilation,
BDD/bitset optimization, and new live experiments.

## 1. Executable semantic chain

The production semantic chain remains:

`ClaimSpec -> q_{C,H} -> CompiledEvidenceSemantics -> q[Omega(e)] -> S-/S+ -> VALID/INVALID/UNRESOLVED -> R*`.

Predictive witness synthesis is a **diagnostic/explanation product of q**. It does
not sit between adjudication and R* and does not alter reuse entitlement.

## 2. Bounded q semantics remain unchanged

For deterministic input-enabled targets:

`q_{C,0}(s) = current claim-projected output`

and for `h >= 1`:

`q_{C,h}(s) = (current output, q_{C,h-1}(next(s,u)) for every admitted u)`.

Only declared layers `0..H` are compiled. The definition oracle independently
enumerates continuation words and projected output-trace laws.

## 3. Evidence semantics remain compiler-owned

Production observation authoring remains forward:

`O(w) = set of retained-evidence tokens possible in modeled world w`.

ReplayMark derives `Omega(e) = {w : e in O(w)}` over the complete declared target
world domain. Naked hand-authored `EvidenceSpec` remains low-level/oracle IR and
cannot enter the production evidence-image path.

The compiler guarantees exact inversion relative to the model. Adapter authors
remain responsible for conservative semantic adequacy to reality:
`Omega_real(e) subseteq Omega_model(e)`.

## 4. Support, adjudication, and R* remain unchanged

For compatible worlds `Omega(e)`:

`S_C^-(e) = intersection_w S_C(w)`

`S_C^+(e) = union_w S_C(w)`.

For recorded projected action `z`:

- `VALID` iff `z in S_C^-(e)`;
- `INVALID` iff `z notin S_C^+(e)`;
- `UNRESOLVED` otherwise.

Fixed-evidence maximal certified reuse is:

`R*(e,z) = REUSE iff z in S_C^-(e)`.

`DO_NOT_REUSE` remains a theorem conclusion about reuse entitlement, not a
fallback or regeneration command.

## 5. Witness semantics are now explicitly split

ReplayMark has two different constructive explanations.

### 5.1 Predictive continuation witness

A predictive witness is defined for a **pair of target decision worlds**. It is a
shortest admitted continuation word whose claim-projected output traces differ.

It proves:

> these two worlds are not equivalent under bounded `q_{C,H}`.

It depends on target semantics, claim projection, continuation alphabet, and q
horizon. It does **not** depend on evidence, a historical action, support, verdict,
or R*.

### 5.2 R* counterexample world

An R* counterexample is defined for **one evidence/action pair `(e,z)`**. It is a
raw `w in Omega(e)` where `z` is not positively supported.

It proves:

> reusing this historical action under this evidence would be support-unsound.

It is a raw world, not a continuation sequence, and carries no shortest-word
semantics.

The generic term `witness` must not erase this distinction.

## 6. Production predictive-witness synthesis

`replaymark/predictive_witness.py` consumes only a sealed `BoundedQuotient`; it
does not call the TargetModel again.

For a pair first separated at q depth `d`:

- `d=0`: the empty continuation word is the shortest witness because current
  projected outputs already differ;
- `d>0`: a continuation that sends the pair to worlds already separated at
  `q_{C,d-1}` is a refinement backpointer. Production prepends that continuation
  to the already-shortest successor witness.

Because q equality at depth `d-1` means equality for **every** continuation word
of length at most `d-1`, first separation at depth `d` proves global minimum
witness length `d`. This is not a greedy heuristic.

Among multiple equal-length shortest words, the declared TargetModel continuation
order is the canonical tie break. Changing that order may change serialized
witness choice but not q equivalence or minimum length.

## 7. Production predictive certificate

`PredictiveContinuationWitness` is bound to quotient and claim fingerprints and
stores:

- canonical unordered state pair;
- selected compiled depth;
- first separation depth;
- shortest continuation word;
- complete left projected trace; and
- complete right projected trace.

`PredictiveWitnessIndex` contains exactly one certificate for each state pair
separated by the selected q layer and none for equivalent pairs.

Production validates q-refinement monotonicity, q0/current-output consistency,
complete successor rows, successor-domain closure, justified splitters/backpointers,
first-separation-depth equality with word length, and actual trace separation.
Unknown states and uncompiled deeper horizons fail closed.

## 8. Independent definition check

The production algorithm uses refinement backpointers. The existing definition
oracle uses a materially different algorithm:

`shortest_distinguishing_word` enumerates continuation words by increasing length
and directly evaluates exact projected output-trace laws.

For deterministic targets the two must return the exact same canonical word under
the declared continuation order. The oracle imports no production witness module.

Accordingly the right description remains **algorithmically independent
definition oracle above a shared semantic-contract TCB**.

## 9. Canonical examples

Production must reproduce the frozen Better Thermostat witnesses:

- N2b: `presence_toggle`, first separation depth 1;
- depth-2 pair: `presence_toggle -> night_toggle`, first separation depth 2.

A pair with different current projected outputs produces the empty word at depth
0.

An equal-length tie fixture proves that reversing only declared continuation order
changes canonical witness choice from the first symbol to the other while leaving
minimum length and inequivalence unchanged.

## 10. CompiledContract seed warning

The early seed protocol still contains:

`shortest_witness(observation, historical_action)`.

The research now shows that this signature conflates two distinct semantics. It
**must not be implemented as written** in any concrete contract.

The later CompiledContract API re-freeze must expose predictive continuation
witnesses separately from R* counterexample worlds. This branch deliberately does
not perform that API re-freeze yet.

## 11. Admitted verification

This branch closes only if all prior semantic gates remain green and the new
production witness stage also passes:

- canonical Better Thermostat depth-1 and depth-2 witnesses;
- empty-word current-output separation;
- symmetric pair lookup;
- declared-order tie-break behavior;
- malformed q artifact and depth/domain fail-closed checks;
- structural separation from R* raw-world counterexamples;
- exhaustive verification of all **5,832** complete 3-state / 2-continuation /
  2-output deterministic machines, all three unordered state pairs, at q depths
  0,1,2,3: **69,984 production-vs-definition witness queries**;
- exact word equality with the independent definition oracle;
- first separation depth equal to shortest word length, with all shallower q
  layers merging the pair;
- independent trace-law equality for both stored traces; and
- symmetry checked for every exhaustive pair-depth query.

## 12. Next boundary

Do not instantiate the final `CompiledContract` yet.

The remaining pre-packaging hardening is now:

1. derive a compiler-observed digest of full target semantics rather than relying
   only on a provider fingerprint; and
2. re-freeze the `CompiledContract` API around the semantics actually established.

Runtime raw-observation tokenization, execution fallback policy, and live E3b
intervention remain subsequent steps.
