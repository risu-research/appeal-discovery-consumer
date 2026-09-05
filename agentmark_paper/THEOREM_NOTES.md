# AgentMark — Theorem / Proof Notes for PerCom

Status: internal proof discipline for `agentmark-theory-lock`. These notes separate genuinely proved statements from definitions, classical inequalities, and empirical claims.

## 1. Setup

Fix one controller decision state `s` and a predeclared projection `phi`. Let

`K(e | y) := K_s^phi(e | y)`

be a Markov kernel from feedback alphabet `Y` to projected controller-event alphabet `E`.

Let source and target environments induce feedback laws `mu` and `nu` over `Y`.

The corresponding live controller-induced workload laws are

`P := mu K`, `Q := nu K`,

where

`P(e) = sum_y mu(y) K(e|y)`.

The projection is part of the theorem statement. Changing projection can change both equivalence classes and replay-validity verdicts.

## 2. Definition: local source-consistency and target admissibility

For a recorded projected event `e` at an aligned controller state:

- source-consistent iff `K(e | y_S) > 0`;
- target-admissible iff `K(e | y_T) > 0`;
- support failure iff source-consistent and not target-admissible.

This is a definition / immediate support criterion, not a deep theorem. The paper should not oversell it.

A multi-step replay requires prefix-conditioned target state alignment. If target-conditioned prior decisions move the controller to another state, the next check must use that target state. The current single-state E3b/E3c decisive witness does not license a theorem that reuses source states for arbitrary divergent traces.

## 3. Definition: feedback decision-equivalence

For fixed `s, phi`, define

`y ~ y'` iff `K(.|y) = K(.|y')`.

This is an equivalence relation because equality of distributions is reflexive, symmetric, and transitive.

Let the quotient cells be `C_1, ..., C_m`.

## 4. Proposition: quotient sufficiency for deterministic controllers

Assume the projected controller is deterministic: for each feedback `y`, `K(.|y)` is a point mass at `g(y)`.

Then the decision-equivalence cells are exactly the inverse images of distinct projected events under `g`.

For any feedback law `mu`, define quotient law

`bar_mu(C_j) = sum_{y in C_j} mu(y)`.

Then the induced workload law is isomorphic to the quotient law:

`(mu K)(e_j) = bar_mu(C_j)`

for every distinct projected event `e_j`.

Therefore, for any source/target feedback laws `mu, nu`,

`TV(mu K, nu K) = TV(bar_mu, bar_nu)`.

### Proof

Because the controller is deterministic, for each quotient cell `C_j` there is one projected event `e_j` such that `g(y)=e_j` for every `y in C_j`, and distinct cells correspond to distinct projected events. Thus

`(mu K)(e_j) = sum_y mu(y) 1[g(y)=e_j] = sum_{y in C_j} mu(y) = bar_mu(C_j)`.

The mapping `C_j <-> e_j` is bijective over represented cells/events, so

`1/2 sum_e |(mu K)(e) - (nu K)(e)|`

is exactly

`1/2 sum_j |bar_mu(C_j) - bar_nu(C_j)|`.

QED.

### Paper interpretation

This result says the relevant environmental shift is not raw feedback drift. It is feedback probability mass crossing controller-decision classes. Feedback changes entirely within a decision class are semantically invisible at projection `phi`.

## 5. Corollary: feedback-insensitive safety at a decision point

If all supported feedback symbols belong to one decision-equivalence class, then for every pair `mu,nu`,

`mu K = nu K`

and

`TV(mu K, nu K)=0`.

For deterministic controllers this is immediate from the proposition. More generally it holds whenever all `K(.|y)` are identical.

This is the formal prediction exercised by AgentMark's feedback-insensitive negative control.

## 6. Proposition: injective deterministic extreme

If the deterministic mapping `g` is injective on the supported feedback alphabet, every decision-equivalence class is a singleton and

`TV(mu K, nu K) = TV(mu,nu)`.

Thus no feedback-law contraction occurs at that decision point.

This is useful as an exact sanity extreme, not a central novelty claim.

## 7. Classical contraction bound for stochastic controllers

Define

`eta(K) = max_{y,y'} TV(K(.|y), K(.|y'))`.

Then for any feedback laws `mu,nu`,

`TV(mu K, nu K) <= eta(K) TV(mu,nu)`.

### Status

This is the classical Dobrushin contraction inequality for Markov kernels. **Do not claim it as new.**

### Short proof suitable for an appendix

Take an optimal coupling `(Y,Y')` of `mu,nu`, so

`Pr[Y != Y'] = TV(mu,nu)`.

Conditionally couple outputs from `K(.|Y)` and `K(.|Y')` maximally. If `Y=Y'`, output disagreement probability can be zero. If `Y != Y'`, maximal-coupling disagreement is at most `eta(K)`. Therefore there exists a coupling of `mu K` and `nu K` with disagreement probability at most

`eta(K) Pr[Y != Y'] = eta(K) TV(mu,nu)`.

By the coupling characterization of TV, the claimed bound follows.

## 8. Finite-sample certificate soundness skeleton

Let empirical feedback laws be `hat_mu`, `hat_nu`. Suppose, on event `G`,

`TV(mu,hat_mu) <= r_S`

and

`TV(nu,hat_nu) <= r_T`.

Using Dobrushin contraction,

`TV(mu K, hat_mu K) <= eta r_S`

and

`TV(nu K, hat_nu K) <= eta r_T`.

Let

`D = TV(mu K,nu K)`

and

`D_hat = TV(hat_mu K, hat_nu K)`.

The reverse triangle inequality for a metric gives

`|D-D_hat| <= TV(mu K,hat_mu K) + TV(nu K,hat_nu K)`

so on `G`,

`|D-D_hat| <= eta(r_S+r_T)`.

Define `U = eta(r_S+r_T)` (clipped at one where appropriate). Then on `G`:

`max(0,D_hat-U) <= D <= min(1,D_hat+U)`.

Therefore:

- if `D_hat+U <= epsilon`, then `D <= epsilon` on `G`;
- if `D_hat-U > epsilon`, then `D > epsilon` on `G`;
- otherwise the observations do not resolve the epsilon decision.

If the feedback-law radii jointly hold with probability at least `1-delta`, the SAFE/UNSAFE assertion inherits that confidence under the sampling assumptions used to construct the radii.

## 9. Sampling assumption warning

The current implementation uses Weissman-style finite-alphabet empirical-TV concentration radii. Those bounds require the statistical sampling conditions under which the multinomial empirical law concentration is valid.

The paper must explicitly separate:

1. the deterministic replay/middleware experiment, whose native event counts are exact experimental observations; from
2. the statistical certificate, whose high-confidence interpretation depends on feedback observations satisfying the concentration assumptions.

Do not imply that arbitrary temporally dependent smart-home streams automatically satisfy IID multinomial assumptions. For natural controllers, either construct controlled independent trials, use a dependence-robust bound, or label observational estimates descriptive rather than certified.

## 10. Projection theorem discipline

All statements are relative to projection `phi`.

Example: suppose feedback `home` and `away` both issue `climate.set_preset_mode` but with variants `preset=home` and `preset=away`.

At `operation` projection the two feedback values are equivalent.

At `action=(operation,target_class,variant)` projection they are not equivalent.

Neither verdict is intrinsically "the truth" without a claim about what semantic distinction matters to the benchmark. The paper therefore predeclares projection based on the scientific question and reports sensitivity to coarser projections where useful.

The theory branch regression test requires this exact example: operation-level workload shift is zero while action-level workload shift is one under a complete home-to-away feedback-law swap.

## 11. What may be stated as AgentMark's theorem contribution

Safe wording:

> AgentMark models replay validity through a projected controller kernel. For deterministic controllers, aggregating feedback by controller-decision equivalence is an exact sufficient representation of the induced workload law; for stochastic controllers, a classical Dobrushin coefficient bounds how feedback-law shift propagates to workload-law shift. We combine these facts with finite-sample feedback-law bounds to obtain a replay-specific SAFE/UNSAFE/UNRESOLVED certificate.

Unsafe wording:

> We invent a new total-variation contraction theorem / support theorem.

## 12. Empirical-theory connection

E3b and E3c should be presented as tests of consequences derived from this model, not as proofs of the mathematics.

Their key empirical statements are:

- target feedback crosses an operation-level decision boundary;
- recorded ACT2 is source-consistent but target-unsupported;
- R1 changes timing materially yet retains the unsupported recorded operation;
- R2 re-enters live semantics and changes the native workload;
- feedback-insensitive control remains safe as predicted;
- E3c reproduces the structure on real Home Assistant middleware with independent validation and replication.

Natural-controller experiments should then test new predictions, especially same-operation/different-variant and naturally occurring feedback-equivalence classes.
