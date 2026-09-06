# ReplayMark manuscript patch — support envelope, stochastic scope, and R*

Status: **MANUSCRIPT-READY PREFERRED THEORY FORM**

This patch supersedes the earlier observation-only version. It is designed to add intellectual closure without turning ReplayMark into a new system paper or consuming another experiment.

## A. Preferred compact formalism insertion

### Evidence-conditioned support envelope

Let `e` denote the target evidence retained by the evaluator and let `Omega(e)` be the nonempty set of admitted target conditions `(s,y)` compatible with that evidence. Define

`S_C^-(e) = intersection_{(s,y) in Omega(e)} S_C(s,y)`

and

`S_C^+(e) = union_{(s,y) in Omega(e)} S_C(s,y)`.

`S^-` is the set of projected actions supported in every compatible target world; `S^+` contains those supported in at least one.

**Proposition (exact evidence-conditioned adjudication).** For projected replay action `z`, evidence `e` certifies validity iff `z in S_C^-(e)`, certifies invalidity iff `z notin S_C^+(e)`, and is necessarily unresolved otherwise. In the unresolved case, one target world compatible with the same evidence supports `z` and another excludes it, so no evaluator seeing only `(e,z)` can soundly assign a single binary validity label.

Hence `e` is sufficient to decide support validity for every projected action iff `S_C^-(e)=S_C^+(e)`, equivalently all target worlds compatible with `e` induce the same projected support.

If stronger evidence `e'` eliminates compatible worlds, `Omega(e') subseteq Omega(e)`, then `S^-(e) subseteq S^-(e')` and `S^+(e') subseteq S^+(e)`: stronger evidence can only shrink the unresolved band.

### One-sentence interpretation

ReplayMark therefore does not require exact feedback identity; it requires only enough claim-relative target information to collapse uncertainty in the controller property the benchmark claim actually needs.

---

## B. Constructive corollary: selective replay R*

**Corollary (maximal certified reuse).** Given evidence `e`, a replay system can soundly reuse recorded projected action `z` for support claim `C` iff `z in S_C^-(e)`. This is maximally permissive among policies using only `(e,z)`: any policy that reuses outside `S^-` is invalid in at least one target world compatible with the same evidence. If `z notin S^+`, regeneration is required to continue with a target-supported action; if `z in S^+ \ S^-`, the current evidence cannot justify reuse, so the system must obtain stronger evidence, regenerate, or report unresolved.

If naming helps exposition, call this induced rule `R*`. Do **not** present R* as a globally optimal or empirically evaluated replay system. The theorem is the contribution; the label is optional.

### Deterministic specialization

For deterministic controllers, R* reuses exactly when every target world still compatible with the evidence produces the same consequential decision as the recorded action. This makes N2/N2b the two natural boundaries: N2 shows that a coarse claim can merge consequentially distinct decisions, whereas N2b shows that raw feedback differences can be safely ignored when all compatible worlds remain in one consequential decision class.

---

## C. Stochastic-controller scope paragraph

Support validity is an admissibility criterion, not a complete stochastic-fidelity criterion. Let `nu_C` be the replay projected-action distribution, `mu_C` the target distribution, `S=supp(mu_C)`, and `alpha=nu_C(S^c)`. Then

`TV(nu_C,mu_C) >= alpha`,

because `S^c` has target mass zero. Thus positive support violation certifies distributional mismatch. The converse is false: with target `mu_C=(1-epsilon,epsilon)` and replay `nu_C=(0,1)`, every replayed action is support-valid while `TV(nu_C,mu_C)=1-epsilon`, arbitrarily close to one. We therefore use support validity as a minimal semantic gate. Claims about stochastic distributional fidelity require the projected decision law itself to be identified and preserved; support-level R* does not claim otherwise.

---

## D. Contribution integration — preserve the frozen three-contribution structure

Do **not** add an R* contribution or a fourth contribution. The existing three-contribution lock is the right structure.

Fold this theory into the existing contributions as follows:

- **C1 remains the conceptual contribution:** controller-conditioned, claim-relative replay validity. The support envelope sharpens exactly what target information is sufficient for that validity judgment.
- **C2 remains the operational contribution:** executable replay-validity audit. R* is a constructive corollary of C2's fail-closed audit contract: certified-valid actions may be reused; certified-invalid actions must be replaced; unresolved actions require refinement/regeneration/fail-closed handling.
- **C3 remains the empirical contribution:** the existing two-sided pervasive-systems evidence plus the promoted downstream/default-capacity engineering consequence.

If a single phrase is needed in C2, use something like:

> "The same evidence-conditioned criterion induces a maximally permissive sound selective-reuse rule without requiring raw-feedback identity."

That is enough. Do not advertise R* as an independently implemented system.

---

## E. Reviewer attack preemption

Potential attack: "ReplayMark seems to require exact feedback replay."

Answer: No. The envelope criterion is strictly claim-relative. Exact raw feedback is unnecessary whenever all target worlds compatible with the retained evidence induce the same relevant support/decision class. N2b demonstrates that boundary empirically.

Potential attack: "If evidence is incomplete, aren't your validity labels guesses?"

Answer: No. ReplayMark explicitly has a three-valued boundary: certified valid, certified invalid, or unresolved. The unresolved region is not a confidence heuristic; it is the exact set on which identical evaluator evidence is compatible with both labels.

Potential attack: "Why is R* anything more than a heuristic?"

Answer: Its reuse set is theorem-induced. A support-sound policy using only the current evidence cannot reuse outside `S^-`; R* reuses everywhere inside `S^-`. It is therefore maximally permissive for the stated support-validity objective without requiring an arbitrary similarity threshold.

Potential attack: "Why not always regenerate unresolved actions?"

Answer: That is safe but not universally cost-optimal. Stronger evidence may resolve the ambiguity more cheaply. ReplayMark therefore states the correctness boundary and deliberately leaves evidence-acquisition/regeneration cost optimization to a system with an explicit cost model.

Potential attack: "Positive support is too weak for a stochastic controller."

Answer: Correct, and the paper says so. Support success is only admissibility; the TV counterexample shows that full probability fidelity is strictly stronger.

---

## F. Page-budget recommendation

Preferred main-body footprint:

- support-envelope proposition + sufficiency sentence: about 120--150 words;
- R* constructive corollary: about 80--100 words;
- stochastic-scope inequality + counterexample: about 80--100 words.

Target total: roughly 0.30--0.45 technical page after notation reuse.

If space is tight, keep the proposition, the R* corollary, and one stochastic-scope sentence/counterexample. Do not add a new experiment. Do not spend space presenting R* as a standalone system architecture.
