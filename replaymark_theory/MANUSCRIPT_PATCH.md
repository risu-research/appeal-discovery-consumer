# ReplayMark manuscript patch — support sufficiency + stochastic scope

Status: **MANUSCRIPT-READY CANDIDATE**

This patch is designed to fit the existing formalism with minimal page cost. It should be edited only for notation/style consistency with the final LaTeX source.

## A. Compact proposition for the formalism section

### Observation sufficiency

Let `eta:Y->O` be an observation abstraction. We call `eta` **support-sufficient** for claim `C` when, at fixed target state `s`, any two observations merged by `eta` induce the same projected support:

`eta(y)=eta(y') => S_C(s,y)=S_C(s,y')`.

**Proposition (exact support observability).** There exists an exact validity test `Vhat_C(s,eta(y),z)` using only the retained observation `eta(y)` such that `Vhat_C(s,eta(y),z)=1{z in S_C(s,y)}` for every admitted target condition and projected action `z` iff `eta` is support-sufficient. Sufficiency follows by defining the support on each abstraction class; necessity follows because if two merged observations have different supports, an action in their symmetric difference must receive different validity labels from identical evaluator inputs.

A stronger notion is **decision sufficiency**, `eta(y)=eta(y') => mu_C(.|s,y)=mu_C(.|s,y')`. Decision sufficiency implies support sufficiency, but not conversely: two target distributions may have the same support and different probabilities.

### Suggested bridge sentence

Thus the information a valid replay must preserve is claim-relative: raw-feedback equality can be unnecessarily strong, while an abstraction that merges observations with different projected supports is provably too coarse for exact support adjudication.

---

## B. Stochastic-controller scope paragraph

Support validity is an admissibility criterion, not a complete stochastic-fidelity criterion. Let `nu_C` be the replay's projected-action distribution at a fixed target condition, let `mu_C` be the target distribution, and let `S=supp(mu_C)`. If `alpha=nu_C(S^c)` is replay mass outside target support, then

`TV(nu_C,mu_C) >= alpha`,

because the event `S^c` has target mass zero. Hence any positive support violation certifies distributional mismatch. The converse is false: with target `mu_C=(1-epsilon,epsilon)` and replay `nu_C=(0,1)`, every replayed action is support-valid but `TV(nu_C,mu_C)=1-epsilon`, arbitrarily close to one. We therefore use support validity as a minimal semantic gate; claims about stochastic distributional fidelity require a stronger comparison of projected decision laws.

---

## C. One-sentence empirical synthesis using existing cases

N2 and N2b expose both sides of this criterion: N2 shows that an abstraction sufficient for an operation-level claim can become insufficient under a finer consequential projection, whereas N2b shows that different raw feedback need not matter when it lies inside the same projected decision-equivalence class.

---

## D. Contribution-list candidate

- **Claim-relative sufficiency.** We characterize exactly when a retained observation abstraction is sufficient to adjudicate support validity and distinguish this minimal admissibility condition from full stochastic decision fidelity.

Use this contribution bullet only if the proposition remains in the final paper body; otherwise leave it as discussion material rather than inflating the contribution list.

---

## E. Reviewer attack preemption

Potential attack: "ReplayMark seems to require replaying all feedback exactly."

Answer: No. Proposition 1 identifies the exact condition under which an observation abstraction is enough. N2b is the constructive boundary showing raw differences can be safely quotiented when they preserve the relevant decision class.

Potential attack: "Positive support is too weak for a stochastic controller."

Answer: Correct, and the paper should say so explicitly. Support validity is intentionally the admissibility floor. The TV lower bound makes support failure decisive while the two-action counterexample proves that support success is not claimed to establish probability fidelity.

Potential attack: "Then why not use TV everywhere?"

Answer: TV requires the target projected decision distribution itself to be identifiable or estimable. ReplayMark's support criterion is useful exactly because some claims need only rule out actions the target controller would not generate, and deterministic/structural controller semantics can establish such exclusions without estimating a full stochastic law.

---

## F. Page-budget recommendation

Keep the main-paper insertion under about 180--230 words plus one displayed inequality if possible. Do not add a new experiment. If space is tight, retain the exact-observability proposition and the stochastic counterexample; move the refinement corollary to prose or omit it because the existing projection-refinement result already carries related intuition.