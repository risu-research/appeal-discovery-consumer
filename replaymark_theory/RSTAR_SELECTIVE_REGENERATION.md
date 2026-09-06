# ReplayMark R* — theorem-induced selective regeneration

Status: **CONSTRUCTIVE COROLLARY / MANUSCRIPT CANDIDATE; NOT AN IMPLEMENTED-SYSTEM CLAIM**

This note derives the cleanest possible selective replay rule from the already-frozen support-envelope result. The goal is not to add a heuristic system. It is to show that ReplayMark's validity criterion induces a canonical reuse boundary under incomplete target evidence.

The scientific claim is deliberately narrow:

> For claim-relative **support validity**, R* is the maximally permissive replay rule that can certify reuse from the currently retained evidence alone.

It does **not** claim global cost optimality, stochastic distributional fidelity, or an evaluated production implementation.

---

## 1. Setup inherited from the support envelope

Let `e` be the target evidence available at the replay decision point and let

`Omega(e)`

be the nonempty set of admitted target conditions still compatible with that evidence.

For claim `C`, each compatible target condition `w` induces projected target support

`S_C(w)`.

Define

`S_C^-(e) = intersection_{w in Omega(e)} S_C(w)`

and

`S_C^+(e) = union_{w in Omega(e)} S_C(w)`.

For the recorded/replayed projected action `z`, the support-envelope proposition gives exactly three evidence states:

- `z in S^-`: supported in every compatible target world;
- `z notin S^+`: supported in no compatible target world;
- `z in S^+ \ S^-`: supported in some compatible worlds and excluded in others.

---

## 2. Fixed-evidence support-sound replay policies

A fixed-evidence selective replay policy `rho(e,z)` may either `REUSE` the recorded projected action or `DO_NOT_REUSE` it.

Call `rho` **support-sound** if

`rho(e,z) = REUSE`

implies

`z in S_C(w)` for every `w in Omega(e)`.

This is the natural safety requirement when the evaluator has only evidence `e`: a reuse decision must remain support-valid in every target condition the evidence still admits.

---

## 3. Proposition: R* is the maximally permissive support-sound reuse rule

Define

`R*(e,z) = REUSE  iff  z in S_C^-(e)`.

### Proposition

`R*` is support-sound. Moreover, for every support-sound fixed-evidence policy `rho`,

`rho(e,z) = REUSE  =>  R*(e,z) = REUSE`.

Equivalently, no sound policy that sees only `(e,z)` can reuse on any additional evidence/action pair beyond R*.

### Proof

If `R*` reuses, then `z in S^-`, so by definition `z` belongs to every support `S_C(w)` for `w in Omega(e)`; hence reuse is support-sound.

Conversely, suppose a support-sound policy `rho` reuses at `(e,z)`. Soundness requires `z in S_C(w)` for every compatible `w`. Therefore `z` lies in their intersection `S^-`, so `R*` also reuses. QED.

### Meaning

This is stronger and cleaner than saying "regenerate when feedback changes." Raw feedback may change without affecting the relevant support class (N2b), while apparently similar feedback may still leave consequentially different supports under a finer claim (N2). R* reuses exactly when the available evidence is strong enough to certify the recorded consequence across all admitted target worlds.

---

## 4. Canonical three-way policy

The binary theorem identifies the exact reuse set. For an executable replay workflow, the support envelope induces the following three-way rule:

1. **REUSE** if `z in S^-`.
2. **REGENERATE** if `z notin S^+`.
3. **REFINE-OR-REGENERATE** if `z in S^+ \ S^-`.

The third branch is intentionally not collapsed into an optimization claim.

- Reuse is unsound under the current evidence because at least one compatible world excludes `z`.
- Immediate regeneration is safe, but may be unnecessarily expensive if stronger evidence can cheaply collapse the ambiguity.
- Therefore the scientifically correct statement is that the current evidence cannot justify reuse. A system may obtain stronger evidence, invoke the target controller, or fail closed / report unresolved depending on its cost and availability model.

There is no universal theorem that immediate regeneration is cost-optimal without an explicit cost model, so ReplayMark should not make that claim.

---

## 5. Adaptive evidence refinement

Suppose a workflow can acquire stronger evidence `e'` with

`Omega(e') subseteq Omega(e)`.

Then the support-envelope monotonicity result gives

`S^-(e) subseteq S^-(e')`

and

`S^+(e') subseteq S^+(e)`.

Hence an unresolved recorded action can only move toward one of two certified outcomes as evidence improves:

- into guaranteed support, where reuse becomes certified; or
- outside possible support, where regeneration becomes certified necessary if execution is to continue with a target-supported action.

An adaptive R* workflow may therefore repeat:

`evaluate envelope -> refine evidence if unresolved -> reuse/regenerate when certified`.

Any refinement strategy remains support-sound so long as it reuses only after membership in the current `S^-` has been established.

This is a correctness statement, not a claim that any particular evidence-acquisition order minimizes latency or cost.

---

## 6. Deterministic-controller specialization

For a deterministic projected controller, every compatible world has singleton support

`S_C(w) = {g_C(w)}`.

Then R* reuses `z` iff every target world compatible with the current evidence agrees that

`g_C(w) = z`.

Thus the deterministic specialization is especially intuitive:

> Reuse is certified exactly when the consequential decision is invariant over all target worlds the evidence has not ruled out.

If compatible worlds disagree, the evidence is insufficient; if all agree on a different action, the recorded action is certified invalid.

This is the setting of the paper's decisive E3b/E3c/N1/N2 witnesses.

---

## 7. N2 and N2b as constructive boundary cases

### N2 — why a coarse reuse rule can be unsound

At an operation-only projection, multiple target worlds can appear equivalent because both issue the same operation to the same thermostat. Under the consequential projection, however, `home` and `away` belong to different action classes. If the retained evidence admits both consequential outcomes, the recorded action falls in the unresolved band rather than `S^-`; R* correctly refuses to certify reuse.

### N2b — why raw-equality replay can be overconservative

The raw target feedback differs, but all compatible observations induce the same consequential controller decision. The projected action therefore remains in `S^-`, so R* certifies reuse even though exact raw-feedback identity fails.

Together the cases show why R* is neither "always replay" nor "always regenerate on any feedback difference." It quotients exactly the distinctions that the benchmark claim permits.

---

## 8. Stochastic-controller scope

R* above is a **support-validity** policy. For stochastic controllers it guarantees only that a reused projected action is not excluded by any target law compatible with the evidence.

It does not guarantee that repeated replay samples follow the target distribution.

A fixed recorded draw can be support-valid while badly distorting target probabilities. Therefore:

- for an admissibility claim, support-level R* is the correct selective reuse rule;
- for a stochastic distributional-fidelity claim, the evidence must identify the required projected decision law (decision sufficiency), and the replay mechanism must preserve/sample from that law rather than merely reuse a support-admissible recorded draw.

This scope distinction is mandatory. It prevents R* from silently upgrading the paper's support criterion into a stronger stochastic-fidelity claim.

---

## 9. What R* contributes — and what it does not

### Legitimate contribution

ReplayMark's information criterion is constructive: the guaranteed-support envelope induces a unique maximally permissive sound reuse set under the current evidence.

This closes the conceptual loop:

`claim -> consequential projection -> compatible target worlds -> support envelope -> certified reuse / invalidity / unresolved`.

### Claims to avoid

Do **not** say that R* is:

- a globally optimal replay algorithm;
- an implementation already evaluated in the paper;
- a complete stochastic-fidelity mechanism;
- guaranteed to reduce runtime or controller invocations in all workloads; or
- universally preferable to R0/R1/R2.

Without a cost model and an implementation study, those would be unnecessary overclaims.

---

## 10. Recommended main-paper form

The strongest page-efficient presentation is a short corollary immediately after the support-envelope proposition:

> **Corollary (maximal certified reuse).** Given target evidence `e`, a replay system can soundly reuse a recorded projected action `z` for support claim `C` iff `z` lies in the guaranteed support `S_C^-(e)`. This rule is maximally permissive among policies using only `(e,z)`: any policy that reuses outside `S_C^-(e)` is invalid in at least one target world compatible with the same evidence. Actions outside `S_C^+(e)` require regeneration to continue with a target-supported action; actions in `S_C^+(e) \ S_C^-(e)` require stronger evidence, regeneration, or an unresolved outcome.

Expected main-text cost: about 80--110 words after notation is already introduced.

If page pressure is severe, call this a constructive corollary rather than introducing R* as a full named system. If the manuscript has enough room, `R*` can be used as a mnemonic label, but the theorem—not the label—is the contribution.
