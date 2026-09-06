# ReplayMark support-envelope proposition

Status: **HIGH-VALUE THEORY CANDIDATE / PREFERRED MAIN-PAPER FORM**

This is a stronger operational form of the observation-support sufficiency result because it directly matches ReplayMark's supplied-state / observed-prefix / model-prefix evidence hierarchy and yields an exact three-valued adjudication rule under incomplete evidence.

## 1. Evidence-compatible target conditions

Let `e` denote whatever target evidence the evaluator actually has: a supplied state, an observed prefix, a model-constrained prefix, or any other retained evidence object.

Let `Omega(e)` be the nonempty set of admitted target conditions `(s,y)` still compatible with `e` under the paper's evidence contract.

For claim `C`, each compatible target condition has projected support

`S_C(s,y) = supp(mu_C(.|s,y))`.

Define the **guaranteed support** and **possible support** induced by evidence `e`:

`S_C^-(e) := intersection_{(s,y) in Omega(e)} S_C(s,y)`

`S_C^+(e) := union_{(s,y) in Omega(e)} S_C(s,y)`.

Thus `S^-` contains projected actions supported in every target world still compatible with the evidence, while `S^+` contains actions supported in at least one compatible world.

---

## 2. Proposition: exact three-valued support adjudication

For any projected replay action `z`:

1. if `z in S_C^-(e)`, then `z` is support-valid in **every** target condition compatible with `e`;
2. if `z notin S_C^+(e)`, then `z` is support-invalid in **every** compatible target condition; and
3. if `z in S_C^+(e) \ S_C^-(e)`, then the evidence is **insufficient to decide** exact support validity: there exists a compatible target condition in which `z` is supported and another compatible target condition in which it is not.

Therefore the maximally informative sound adjudicator from evidence `e` is exactly:

- `CERTIFIED_VALID` if `z in S^-`;
- `CERTIFIED_INVALID` if `z notin S^+`;
- `UNRESOLVED` otherwise.

### Proof

(1) follows immediately from intersection membership.

(2) follows immediately from absence from the union.

For (3), `z in S^+` gives at least one compatible condition whose support contains `z`; `z notin S^-` gives at least one compatible condition whose support excludes `z`. Since both conditions are consistent with the same evidence `e`, no evaluator that sees only `e` and `z` can soundly return a single binary validity label for both. QED.

---

## 3. Corollary: exact support sufficiency criterion

Evidence `e` is sufficient to determine support validity for **every** projected action iff

`S_C^-(e) = S_C^+(e)`.

Equivalently, every target condition compatible with `e` induces the same projected support.

This is the evidence-set form of the observation-abstraction proposition: an abstraction is support-sufficient exactly when each abstraction fiber has identical target support.

---

## 4. Monotonicity under stronger evidence

Suppose `e'` is strictly more informative than `e`, so

`Omega(e') subseteq Omega(e)`.

Then

`S_C^-(e) subseteq S_C^-(e')`

and

`S_C^+(e') subseteq S_C^+(e)`.

Hence stronger admissible evidence can only enlarge the set of actions certified valid and shrink the set of actions that remain possibly valid. The unresolved band

`S_C^+(e) \ S_C^-(e)`

can only shrink as compatible target worlds are eliminated.

This gives a formal justification for the paper's evidence hierarchy: supplied-state, observed-prefix, and model-prefix evidence are useful exactly insofar as they reduce the compatible-world set enough to collapse consequential support uncertainty.

---

## 5. Why this is stronger than requiring exact feedback replay

The proposition does not require exact recovery of the raw target observation.

- If all compatible raw observations yield the same projected support, the evidence is already sufficient even though raw feedback remains ambiguous.
- If compatible observations disagree on projected support, then no evaluator using that evidence alone can exactly decide validity, regardless of implementation sophistication.

This is the sharp information boundary ReplayMark needs.

---

## 6. Relationship to N2 and N2b

### N2

Under a coarse operation-only claim, the compatible target conditions may collapse to the same projected support even though consequential parameters differ. Under the finer consequential claim, the same evidence can leave different supports, creating a nonempty unresolved band. This makes support sufficiency claim-relative.

### N2b

Raw feedback differs, but the controller makes the same projected decision. The compatible worlds therefore share the same projected support/decision law for the evaluated claim, so raw equality is unnecessary.

Together they instantiate both sides of the envelope criterion.

---

## 7. Direct bridge to selective regeneration R*

The envelope proposition yields a principled selective policy without yet claiming an implementation:

- if the recorded projected action lies in `S^-`, reuse is semantically certified for the support claim;
- if it lies outside `S^+`, reuse is certified invalid and regeneration is required;
- if it lies in `S^+ \ S^-`, the current evidence cannot justify reuse, so a conservative system must obtain stronger evidence, regenerate through the target controller, or report unresolved.

This is better than a heuristic "replay when similar, regenerate when different" rule because every branch is tied to a necessary-and-sufficient information condition.

---

## 8. Main-paper recommendation

Prefer this support-envelope proposition over a longer abstract discussion of observation abstractions if page pressure is severe. It simultaneously:

- answers how much target feedback is enough;
- formalizes the evidence hierarchy;
- explains why some raw differences do not matter;
- proves when incomplete evidence is fundamentally insufficient; and
- sets up `R*` almost mechanically.

A compact statement plus proof sketch can fit in roughly 140--180 words. The stochastic-scope TV bound should remain a separate short paragraph.