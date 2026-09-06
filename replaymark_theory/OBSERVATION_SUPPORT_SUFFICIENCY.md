# ReplayMark theory closure: observation/support sufficiency and stochastic scope

Status: **THEORY CANDIDATE FROZEN FOR MANUSCRIPT INTEGRATION**

This note closes two reviewer-facing gaps without changing any frozen empirical result:

1. what observation information is *exactly sufficient* to decide claim-relative support validity; and
2. what support validity does and does not establish for stochastic controllers.

The result is intentionally claim-relative and uses the same projected target-controller distribution already used by ReplayMark.

---

## 1. Setup

Let:

- `A` be the raw action space;
- `phi_C : A -> Z_C` be the consequence projection for claim `C`;
- `pi_T(. | s,y)` be the target controller's action distribution at target state `s` and observation `y`;
- `mu_C(. | s,y) := (phi_C)# pi_T(. | s,y)` be the projected target decision distribution on `Z_C`;
- `S_C(s,y) := supp(mu_C(. | s,y))` be its projected support.

ReplayMark's stepwise support-validity predicate for projected replay action `z` is

`V_C(s,y,z) = 1{ z in S_C(s,y) }`.

For the manuscript's finite/discrete action alphabets, support is simply the set of projected actions with positive target probability. The claims below are therefore elementary finite-space statements; no measure-theoretic regularity assumptions are needed.

Let `eta : Y -> O` be an observation abstraction: the evaluator retains only `o = eta(y)` rather than the full target observation `y`.

We restrict all statements to an admitted domain `D` of `(s,y)` pairs. This matters: sufficiency is always relative to the state/observation region for which evidence is claimed.

---

## 2. Support sufficiency

### Definition 1 (claim-relative support sufficiency)

An observation abstraction `eta` is **support-sufficient for claim C on D** iff for every admitted `s,y,y'`,

`eta(y) = eta(y')  =>  S_C(s,y) = S_C(s,y')`.

Equivalently, target projected support is constant on every admitted fiber of `eta` at fixed state `s`.

This is weaker than requiring raw-observation equality and weaker than requiring equality of the full stochastic decision distribution.

---

## 3. Exact observation criterion

### Proposition 1 (support-sufficiency iff exact support validity is observable)

There exists an evaluator

`Vhat_C(s, eta(y), z)`

that uses only target state `s`, retained observation `eta(y)`, and projected replay action `z`, and satisfies

`Vhat_C(s, eta(y), z) = V_C(s,y,z)`

for **every** admitted `(s,y)` and every projected action `z in Z_C`

**iff** `eta` is support-sufficient for claim `C` on `D`.

#### Proof

**Sufficiency.** If support is constant on each `eta`-fiber, define

`Shat_C(s,o) := S_C(s,y)`

for any admitted `y` with `eta(y)=o`. Support sufficiency makes this definition independent of the representative. Then

`Vhat_C(s,o,z) := 1{z in Shat_C(s,o)}`

is exact.

**Necessity.** Suppose support sufficiency fails. Then for some fixed admitted state `s`, there exist admitted `y,y'` with the same retained observation `eta(y)=eta(y')` but different supports. Choose

`z in S_C(s,y) triangle S_C(s,y')`.

The true validity of the same projected action `z` differs between `y` and `y'`, while any evaluator receiving only `(s,eta(y),z)` receives identical inputs in the two worlds. Therefore no such evaluator can be exact in both. Contradiction. QED.

### Interpretation

This is the precise answer to the question "how much feedback must replay preserve?"

For a support-validity claim, ReplayMark does **not** require preservation of every raw sensor byte. It requires preservation of enough information to identify the target controller's projected support. Anything coarser is fundamentally insufficient; anything finer may be unnecessary.

---

## 4. Decision sufficiency is stronger

### Definition 2 (claim-relative decision sufficiency)

`eta` is **decision-sufficient for claim C on D** iff

`eta(y)=eta(y')  =>  mu_C(.|s,y)=mu_C(.|s,y')`

for every admitted fixed state `s`.

### Corollary 1

Decision sufficiency implies support sufficiency.

#### Proof

Equal projected distributions have equal supports. QED.

### Strictness

The converse is false. For example, on `Z_C={a,b}`:

- `mu_C(.|s,y)  = (0.9, 0.1)`;
- `mu_C(.|s,y') = (0.1, 0.9)`.

The supports are identical `{a,b}`, so an abstraction that merges `y` and `y'` can remain support-sufficient. But the decision distributions are not equal, so it is not decision-sufficient.

Thus ReplayMark should distinguish two goals:

- **support validity**: is the replayed consequence admissible at all under the target controller?;
- **distributional fidelity**: is replay sampling target consequences with the correct stochastic law?

The first is a minimal semantic gate. The second is strictly stronger.

---

## 5. Claim refinement monotonicity

Suppose claim `C_f` is finer than claim `C_c`, so there exists a deterministic map `q` with

`phi_Cc = q o phi_Cf`.

Then the coarse projected controller is the pushforward

`mu_Cc = q# mu_Cf`.

### Corollary 2

If `eta` is decision-sufficient for the finer claim `C_f`, it is decision-sufficient for the coarser claim `C_c`.

If `eta` is support-sufficient for the finer claim `C_f`, it is support-sufficient for the coarser claim `C_c`.

For the finite alphabets used here, `supp(q#mu)=q(supp(mu))`, so equality of fine supports implies equality of coarse supports.

The converses need not hold.

### Why this matters for ReplayMark

An observation abstraction can be sufficient for an operation-level claim while being insufficient for a consequential-parameter claim. This is exactly the failure mode exposed by N2: preserving only the operation/target identity can hide a consequential parameter change. Sufficiency is therefore not only observation-relative but also **claim-relative**.

---

## 6. Stochastic scope: what support validity certifies

Let `nu_C(.|s,y)` denote the replay system's projected-action distribution at the same target condition and let

`S := supp(mu_C(.|s,y))`.

Define the replay's support-violation mass

`alpha := nu_C(S^c | s,y)`.

### Proposition 2 (support violation lower-bounds distributional mismatch)

Using total variation distance

`TV(nu_C, mu_C) := sup_E |nu_C(E)-mu_C(E)|`,

we have

`TV(nu_C, mu_C) >= alpha`.

#### Proof

Take event `E=S^c`. By definition of target support, `mu_C(S^c)=0`, while `nu_C(S^c)=alpha`. Therefore the supremum over events is at least `alpha`. QED.

### Consequence

A positive support-violation rate is a one-sided certificate of distributional mismatch. In particular, when the target projected controller is deterministic and replay deterministically emits a different projected action, `alpha=1` and hence `TV=1`.

This explains why support failure is already decisive in the deterministic E3b/E3c/N1/N2 witnesses.

---

## 7. Zero support violation does *not* establish stochastic fidelity

### Proposition 3 (support validity can coexist with arbitrarily poor stochastic fidelity)

For every `epsilon in (0,1)`, there exist target and replay distributions with zero support-violation mass but

`TV(nu_C,mu_C) = 1-epsilon`.

#### Construction

Let `Z_C={a,b}` and

- target: `mu_C=(1-epsilon, epsilon)`;
- replay: `nu_C=(0,1)`.

Both actions lie in target support, so `nu_C(S^c)=0`: every replay action is support-valid. But

`TV(nu_C,mu_C)=1-epsilon`,

which approaches 1 as `epsilon -> 0`.

QED.

### Manuscript scope rule

For stochastic controllers, ReplayMark support validity must therefore be described as an **admissibility floor**, not a complete fidelity criterion.

- If support validity fails, replay is semantically incompatible with the target controller under claim `C`.
- If support validity passes, replay may still badly distort target probabilities.
- Claims requiring stochastic distributional fidelity need a stronger criterion, e.g. direct comparison of `nu_C` and `mu_C` where the target law is identifiable.

This is not a defect in the support criterion; it is its intended scope.

---

## 8. How the existing empirical cases instantiate the theory

### N2: same operation, different consequence

N2 shows that a coarse claim projection can merge two actions that a consequential claim must separate. At an operation-only projection, an observation abstraction may appear sufficient; at the consequential-parameter projection it is not. This operationalizes Corollary 2's non-converse.

### N2b: different raw feedback, same decision

N2b is the opposite boundary. Raw target feedback differs, but the controller reaches the same projected decision. Therefore exact raw-feedback equality is stronger than necessary. Locally, an abstraction that merges those feedback values is decision-sufficient for the evaluated claim.

Together N2 and N2b establish both sides of the sufficiency principle:

- preserving too little can merge consequentially distinct target decisions;
- preserving everything can be unnecessarily strict when raw differences lie inside one decision-equivalence class.

---

## 9. Reviewer-facing synthesis

The clean conceptual hierarchy is:

`raw feedback equality`

`    => decision sufficiency`

`        => support sufficiency`

`            => exact support-validity observability`.

The reverse implications do not generally hold.

For ReplayMark, the right preservation target is therefore not raw trace identity. It is the **coarsest claim-relative observation information that preserves the controller property required by the benchmark claim**:

- support, when the claim is admissibility;
- the full projected decision law, when the claim is stochastic distributional fidelity.

This converts the paper's "replay versus regenerate" question into an information requirement rather than a blanket rule to replay or regenerate all feedback.

---

## 10. R* consequence, but not yet a new claim

This theory makes a selective strategy `R*` natural:

- reuse a recorded projected action when the available target evidence certifies that the current target condition shares the required support/decision class and the action is admissible;
- regenerate when the recorded action is excluded;
- fail closed / mark unresolved when the observation evidence is too coarse to certify the required class.

However, `R*` should be developed only after the propositions above are integrated cleanly into the manuscript. The present theory closure does **not** claim that `R*` has already been implemented or evaluated.

---

## 11. Recommended manuscript footprint

The paper does not need all proofs in the main body. A compact high-value version is:

1. one proposition stating Proposition 1;
2. one sentence that decision sufficiency is stronger than support sufficiency;
3. the TV lower bound from Proposition 2;
4. the two-action counterexample from Proposition 3; and
5. one synthesis sentence tying N2/N2b to claim-relative sufficiency.

Expected main-text cost: roughly 0.25--0.40 page if written tightly.

No new experiment is required for these statements.