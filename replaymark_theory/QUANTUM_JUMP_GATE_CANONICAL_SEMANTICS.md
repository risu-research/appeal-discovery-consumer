# ReplayMark quantum-jump gate: from user-declared projection to canonical consequence closure

Status: **THEORY ATTACK / DESIGN GATE — NOT MANUSCRIPT-INTEGRATED**

This note asks a harder question than whether witness coherence is mathematically correct. The only relevant standard is whether the direction can change ReplayMark's intellectual category enough to justify reopening the theory after v31.

## 1. Baseline verdict on witness coherence

Witness coherence is real and useful, but by itself it is **not a quantum jump**.

Why:

1. The core mathematical shape is close to classical forward simulation / trace-conformance reasoning.
2. It repairs composition of local certificates but does not change the paper's most vulnerable modeling choice: the benchmark still has to declare `phi_C` correctly.
3. A reviewer can still ask the deepest question: *who decides which action distinctions are consequential, and how do we know the declared projection is neither too coarse nor unnecessarily fine?*

N2 and N2b empirically demonstrate both sides of that problem, but v31 still treats the correct projection as an input.

Therefore witness coherence should only survive if it becomes a lemma inside a more fundamental result.

---

## 2. The potential quantum jump

The stronger direction is to make ReplayMark answer not only

> Is this recorded action valid under a declared projection?

but also

> **What is the least semantic distinction that a replay must preserve for this benchmark claim to remain sound under target continuation?**

That changes the role of `phi_C` from an arbitrary declaration to the seed of a **canonical closure construction**.

Working name: **consequence closure** or **continuation-stable claim closure**.

---

## 3. Target-conditioned residual consequence semantics

Let `h` be a future-sufficient target execution history/condition. Let `a` be a concrete action executable at that condition. The benchmark supplies an immediate claim projection `phi_C(a)`.

For each `(h,a)`, define the residual claim behavior

`R_C(h,a)`

as the target's admitted future law (or, in a deterministic finite model, future language) of `phi_C`-projected behavior after executing `a` at `h` and thereafter following the target controller/environment semantics in scope.

Two action occurrences are **continuation-equivalent for claim C** when

1. they have the same immediate claim class; and
2. their residual claim behavior is identical.

Symbolically,

`(h,a) ~=*_C (h,b)` iff `phi_C(a)=phi_C(b)` and `R_C(h,a)=R_C(h,b)`.

This is deliberately stronger than one-step action equality and weaker than raw execution identity.

It captures exactly the missing distinction exposed by the witness-incoherence counterexample: two actions can look identical under `phi_C` now but induce distinguishable claim-relevant futures.

---

## 4. Canonical minimality theorem candidate

### Proposition Q1 (coarsest continuation-stable refinement)

For a finite-state target execution model and finite claim projection `phi_C`, there exists a unique coarsest refinement of the declared claim semantics, up to relabeling, that is stable under all admitted target continuations.

Equivalent characterizations:

- equality of residual projected-future languages/laws;
- the greatest continuation-stable relation refining immediate `phi_C` equality;
- the fixed point reached by partition refinement that repeatedly splits same-`phi_C` classes whenever their target-relevant successors have distinguishable refined futures.

Call the resulting contextual semantic map `phi_C^dagger`.

### What this theorem would mean for replay

`phi_C^dagger` is the **least additional semantic information beyond the benchmark's immediate claim projection that makes same-class substitution compositional under the target dynamics**.

This is not a claim that partition refinement or right congruences are new mathematics. The new ReplayMark claim would be that the benchmark projection used for replay has a canonical continuation closure, and that this closure is the exact semantic object required for whole-trace soundness.

---

## 5. Minimal counterexample theorem candidate

### Proposition Q2 (no coarser semantics can guarantee the claim)

If a proposed replay abstraction merges two action occurrences that `phi_C^dagger` separates, then by definition their residual claim behaviors differ. Therefore there exists an admitted distinguishing continuation on which the two executions produce different `phi_C`-projected futures (or different claim-law distributions).

In a finite deterministic model, a shortest distinguishing suffix exists and can be returned as a concrete counterexample witness.

This gives a hard minimality statement:

> Any semantics strictly coarser than `phi_C^dagger` is insufficient to guarantee continuation-level fidelity for claim C.

This is substantially stronger than saying operation identity is sometimes too coarse. It says exactly where the safe coarsening frontier is and produces a witness whenever the frontier is crossed.

---

## 6. Compositionality theorem candidate

### Proposition Q3 (local support becomes trace sound after closure)

Suppose replay compares action occurrences at each target condition using `phi_C^dagger` rather than the raw declared `phi_C`, and target evidence is strong enough to certify the relevant class. Then same-class target support is continuation-stable: substituting a recorded action only when its `phi_C^dagger` class is target-supported preserves target-realizability of the claim-relevant continuation, subject to the declared target execution model.

Operationally, witness coherence is no longer an extra ad-hoc check; it is built into the closed semantic class.

The previous continuation-closure theorem becomes the local proof device for Q3.

---

## 7. Why this is a qualitatively different paper

Current v31:

1. benchmark designer declares `phi_C`;
2. ReplayMark checks target support under that projection;
3. evidence envelopes determine VALID/INVALID/UNRESOLVED;
4. R* reuses only inside guaranteed support.

Quantum-jump version:

1. benchmark designer declares the *claim seed* `phi_C`;
2. ReplayMark computes/checks its canonical target-conditioned consequence closure `phi_C^dagger`;
3. if the seed was too coarse, ReplayMark returns the shortest distinguishing continuation and the minimal required refinement;
4. support envelopes determine what current target evidence can certify under the closed semantics;
5. R* performs maximal sound reuse under that evidence.

The intellectual structure becomes:

`claim seed -> canonical minimal semantics -> evidence sufficiency -> selective reuse -> engineering consequence`.

That is a materially more complete answer to the paper title question than v31.

---

## 8. It directly closes the deepest reviewer attack in v31

Potential reviewer attack on v31:

> ReplayMark is only as correct as the user-supplied projection `phi_C`. N2 and N2b show that granularity matters, but the framework does not tell me how to choose the right granularity.

Current response: the benchmark contract must declare consequential distinctions.

Quantum-jump response:

> The declaration is only the seed. ReplayMark can test whether that seed is stable under target continuation and compute the unique coarsest continuation-stable refinement. If the declared semantics is too coarse, a distinguishing suffix proves exactly why; if it is finer than necessary, the closure quotient identifies which distinctions can be collapsed without changing future claim behavior.

This moves ReplayMark from **audit under a declared semantics** to **synthesis of the minimal semantics needed by the claim**.

---

## 9. Unification of existing experiments

This direction is unusually compatible with the evidence already collected.

### N2

Operation-level identity merges `home` and `away`, but their claim-relevant behavior is already distinguishable at the current action. The closure must split them immediately. N2 is a shortest distinguishing witness for an over-coarse seed.

### N2b

Raw feedback differs, but the target controller produces the same `away` consequence and, under the frozen controller logic in scope, the relevant continuation remains the same. The closure can collapse the raw distinction. N2b is evidence that closure need not preserve raw feedback identity.

### E3b / E3c / N1

The source action path and target controller path diverge after feedback timing changes. The closure must preserve whichever action/continuation distinction separates the source-frozen path from the target-supported path.

### D1 / D2

These establish why crossing the closure boundary matters: an over-coarse replay semantics changes concrete broker provisioning/capacity conclusions.

Thus the existing experiments can be reframed as four layers of one theorem rather than requiring another domain.

---

## 10. Relationship to established theory: novelty line that must not be crossed

The mathematical machinery is not invented here:

- Myhill-Nerode gives canonical right-congruence/minimal residual-language representations.
- simulation/bisimulation and stable-partition algorithms characterize compositional behavioral equivalence.
- MDP homomorphisms/lumpability and causal-state constructions similarly formalize minimal future-predictive abstractions.

Therefore the paper must **not** claim a new general minimization theorem for transition systems.

The possible novelty is the replay/benchmark formulation and the derived methodological object:

> given a benchmark's declared consequential action projection and a target controller, compute the least target-conditioned refinement that makes replay substitution sound under continuation, then combine it with evidence-conditioned support envelopes to decide what can actually be reused.

If that cannot be shown to be distinct from simply “run bisimulation minimization,” this direction should be killed.

---

## 11. Third-pass attack: does the canonical quotient actually exist in the form the paper needs?

### Attack 11.1 — action equivalence is contextual

The same concrete action can have different future effects at different target conditions. Therefore `phi_C^dagger` may need to classify **action occurrences `(h,a)`**, not actions globally.

This is acceptable scientifically but changes the exposition. The paper must not pretend that one context-free action label is always sufficient.

### Attack 11.2 — target environment is open

Future feedback may depend on exogenous behavior. The residual semantics must quantify over the admitted environment model, not over arbitrary impossible suffixes. The closure is therefore relative to a benchmark-declared environment/target model.

This is not a defect; it reinforces claim-relativity. But the contract must say so.

### Attack 11.3 — stochastic law versus support

If continuation equivalence compares full future laws, the result supports distributional trace claims but requires identifiable stochastic dynamics. If it compares only future support languages, it matches the current admissibility floor and is weaker.

A clean PerCom version should likely define **support consequence closure** in the main paper and state the law-preserving analogue separately, preserving v31's stochastic discipline.

### Attack 11.4 — computational cost

Exact residual-language equivalence can be expensive or infinite in arbitrary systems. The main theorem should be bounded to finite declared controller models; practical ReplayMark may use model-prefix or supplied evidence and fail closed when closure cannot be established.

### Attack 11.5 — page-budget risk

If the theory requires a generic automata tutorial, it fails the paper even if correct. To qualify as a quantum jump, the entire concept must replace existing projection/evidence prose, not add a new section.

---

## 12. The strongest possible compact formulation

The entire quantum jump should be expressible with one definition, one theorem, and one algorithmic sentence.

### Definition

Two same-claim action occurrences are continuation-equivalent when no admitted target continuation can distinguish them at the benchmark projection.

### Theorem

Their equivalence classes form the unique coarsest continuation-stable refinement of the declared claim projection. Reuse under any strictly coarser semantics admits a distinguishing continuation; reuse under the closed semantics composes along the target model.

### Constructive consequence

For finite controller models ReplayMark computes the closure by partition refinement and returns a shortest distinguishing suffix when it must split a declared action class.

If this cannot be stated and defended this compactly, do not integrate it.

---

## 13. What would make it genuinely Best-Paper-level rather than merely stronger

All of the following must hold simultaneously:

1. **Canonicality:** not “another criterion,” but the unique/coarsest safe semantic refinement.
2. **Minimality:** every coarser alternative has a concrete distinguishing continuation.
3. **Constructiveness:** the framework can compute the refinement/witness on the finite models already used in the paper.
4. **Unification:** N2 and N2b become empirical witnesses of over-coarse versus unnecessarily fine semantics, while D1/D2 become consequences of crossing the boundary.
5. **Compression:** this replaces prose rather than expanding the paper beyond its current three-contribution spine.
6. **Prior-art honesty:** explicitly ground the construction in congruence/simulation theory and claim novelty only in the replay-specific claim/evidence synthesis.

If any of 1–4 fails, the direction is not a quantum jump and should be killed.

---

## 14. Current quantum-jump verdict

### Witness coherence alone

**NO.** Stronger than v31, but not category-changing.

### Continuation closure alone

**NO.** Useful compositionality condition, still too close to standard simulation reasoning.

### Canonical consequence closure + minimal distinguishing witness + evidence envelope

**YES, POTENTIALLY.** This is the first version of the direction that could change ReplayMark's intellectual category.

The reason is not the automata theorem itself. The reason is that it eliminates the paper's remaining arbitrary semantic input. ReplayMark would no longer merely ask whether replay is valid *given* the right claim projection; it would characterize the **least target-conditioned semantics that the claim itself forces**, prove that nothing coarser can be universally sound, and then determine whether available target evidence is sufficient to certify reuse.

That is a substantially more fundamental answer to “what must replay preserve?”

### Promotion status

**PROMISING BUT NOT YET PROMOTED.** The next gate is not another experiment. It is to instantiate the closure on the existing finite controller models and determine whether:

- the resulting partitions are nontrivial;
- N2/N2b/E3b map cleanly to the predicted splits/merges;
- a shortest distinguishing continuation can be produced without hand-authored semantics;
- the construction remains under ~0.3 page in the main manuscript.

Only if that gate passes should v31 be reopened.
