# AgentMark — PerCom Novelty + Theory Lock

Status: **working lock on `agentmark-theory-lock`**. This document narrows the paper to claims that survive an adversarial prior-art reading. It does not modify or reinterpret the sealed E3b/E3c evidence.

## 1. Primary paper claim

**Timing fidelity is not controller-semantic fidelity.** In a reactive system, a replay may faithfully preserve a recorded action and substantially adapt its timing while executing an action that the live controller, conditioned on target feedback, would not issue at that decision point.

AgentMark turns that failure mode into a replay-validity criterion, a decision-equivalence structure, and a finite-sample certificate, then tests the resulting predictions on real middleware.

The paper must not claim that feedback-aware replay itself is new.

## 2. Formal object

At controller state `s`, let the projected live controller kernel be

`K_s^phi(e | y)`

where `y` is feedback, `e` is a projected controller event/action, and `phi` declares the action granularity being evaluated. The source and target environments induce feedback laws `mu_S` and `mu_T`. Their live workload laws are

`W_S = mu_S K_s^phi`

and

`W_T = mu_T K_s^phi`.

The projection is part of the claim and must be declared before evaluation. AgentMark currently exposes:

- `operation`: operation/service identity only;
- `action`: operation + target class + adapter-declared semantic variant;
- legacy `semantic`: operation + target class + delay;
- `full`: action variant + timing + successor quotient state.

This makes granularity explicit rather than allowing an evaluator to change what counts as "the same action" after seeing results.

## 3. Local replay-admissibility criterion

For a source-recorded event `e` that is source-consistent,

`K_s^phi(e | y_S) > 0`,

that event remains target-admissible at the aligned target decision point iff

`K_s^phi(e | y_T) > 0`.

A **support failure** is therefore

`K_s^phi(e | y_S) > 0` and `K_s^phi(e | y_T) = 0`.

This criterion is deliberately local/prefix-conditioned. A whole-trace theorem must track the target controller state produced by the target-conditioned prefix; the paper must not silently substitute source state for target state when they can diverge.

## 4. Decision-equivalence quotient

At a fixed state and projection,

`y ~_(s,phi) y'`

iff

`K_s^phi(. | y) = K_s^phi(. | y')`.

Raw feedback changes are not sufficient to imply workload changes. Only movement of probability mass across controller-decision equivalence classes can change the live workload under a deterministic controller.

This is the structural explanation for the feedback-insensitive negative control: feedback may change while all relevant feedback values remain in one decision class.

## 5. Deterministic exact-quotient result

For a deterministic projected controller at one decision point, let `c(y)` be the decision-equivalence class/action induced by feedback `y`. Then

`W_mu = c#mu`,

and therefore

`TV(W_S, W_T) = TV(c#mu_S, c#mu_T)`.

The right-hand side is the total-variation distance between source and target feedback laws after aggregation by controller decision class.

This is stronger and more useful for the paper than saying merely that "feedback matters": it identifies exactly which feedback changes are behaviorally irrelevant and which can change the benchmark workload.

## 6. Stochastic sensitivity result

For stochastic controllers define the Dobrushin-style sensitivity

`eta_s^phi = max_(y,y') TV(K_s^phi(.|y), K_s^phi(.|y'))`.

Then

`TV(mu_S K_s^phi, mu_T K_s^phi) <= eta_s^phi * TV(mu_S, mu_T)`.

The contraction inequality itself is classical probability theory and is **not** claimed as a new theorem. AgentMark's contribution is its use as a replay-methodology bridge: controller sensitivity converts an observed feedback shift into a workload-level validity bound.

## 7. Finite-sample certificate

Given empirical source/target feedback laws and valid high-confidence TV radii `r_S`, `r_T`, AgentMark computes the empirical live-workload shift

`D_hat = TV(mu_hat_S K, mu_hat_T K)`

and the uncertainty term

`U = eta * (r_S + r_T)`.

The paper-facing three-way contract is:

- **SAFE at epsilon** when `D_hat + U <= epsilon`;
- **UNSAFE at epsilon** when `D_hat - U > epsilon`;
- **UNRESOLVED** otherwise.

The implementation currently uses Weissman-style multinomial TV radii. The paper must state the sampling assumptions needed by that concentration bound and must not present the certificate as distribution-free with respect to arbitrary temporal dependence.

## 8. Why R0 / R1 / R2 matter

The taxonomy is not the novelty by itself; it is an operational witness for the validity criterion.

- **R0 rigid** freezes recorded semantics and source issue timing.
- **R1 timing-feedback-only** allows target execution/completion timing to move while freezing recorded semantic action identity.
- **R2 semantic-feedback-preserving** re-enters the live controller after target feedback and therefore may change path, operation, target, parameters, or multiplicity.

The decisive empirical point is not merely that R2 executes more work. It is that R1 can look timing-aware while still benchmarking a workload the live target controller would not generate.

E3b/E3c instantiate the strongest support-separation case: target feedback makes the recorded ACT2 unsupported, while semantic replay inserts VERIFY and changes native workload cardinality.

## 9. Parameter-sensitive action identity

A natural controller often keeps the same service/operation name while changing consequential arguments. Example: `climate.set_preset_mode` with `preset=home` versus `preset=away`.

Therefore operation identity cannot be hard-coded as the only semantic granularity. The theory branch adds an adapter-declared opaque `variant` and an `action` projection `(operation, target_class, variant)`.

The generic kernel never interprets the variant. A substrate adapter is responsible for deriving it from externally specified executable semantics before outcome observation. If an adapter cannot derive a stable semantic action identity without guessing, the natural-controller case is excluded rather than manually repaired.

## 10. Prior-art moat: what AgentMark must and must not claim

### Feedback-aware / closed-loop replay

EdgeDroid, CellReplay, NeuralEmu, and closed-loop simulation/emulation work already establish that feedback and workload/environment coupling can matter. AgentMark must cite and embrace this literature, not claim to discover closed-loop dependence.

The distinction to defend is: those systems repair or model domain-specific closed loops; AgentMark asks the cross-domain methodological question **when is a recorded replay itself controller-semantically admissible under changed feedback?** It provides a policy-conditioned validity criterion and certificate that can judge rigid, timing-aware, or domain-specific replay mechanisms.

### Conformance / trace inclusion

Classical conformance testing, ioco-style output inclusion, trace inclusion, and bisimulation already study whether implementations exhibit allowed behavior. AgentMark must not claim that behavioral support/inclusion is new.

The replay-specific contribution is the source-recorded / target-feedback conditioning structure: the same recorded event can be valid under the source controller and invalid under the target-conditioned controller even when replay timing is adapted. AgentMark connects that local failure to workload-level shift and finite-sample environmental evidence.

### Off-policy evaluation / support overlap

Support/absolute-continuity requirements are also standard in off-policy evaluation. AgentMark must not claim support overlap as a new statistical idea. The paper's object is different: validity of a systems replay workload under a changed feedback law, with native middleware consequences and an explicit replay taxonomy.

### Decision fidelity work

Any work that evaluates whether replay reproduces configuration or controller decisions is especially close and must be treated as first-class related work. AgentMark's moat must rest on its explicit controller kernel, projection-dependent support criterion, decision quotient, certificate, and cross-substrate replay semantics rather than the phrase "decision fidelity" alone.

## 11. Claims that are forbidden in the paper

- "Feedback-aware replay is new."
- "Support preservation / trace inclusion is new."
- "The Dobrushin contraction or total-variation inequality is new."
- "AgentMark proves physical-device, radio, Matter, or household validity."
- "Every feedback shift makes replay invalid."
- "Operation names are always sufficient semantic identity."
- "A whole recorded trace is valid merely because every row is checked against the source controller state."
- "E3b's rejected 80 ms endogeneity hypothesis was supported." 

## 12. Reviewer kill tests

The core is not locked until the paper can answer all of these without adding a new story after results are known:

1. **"EdgeDroid/CellReplay/NeuralEmu already preserve feedback."** Answer with replay-validity criterion + decision quotient + certificate + mechanism-independence.
2. **"This is just ioco/trace inclusion."** Answer with source-vs-target feedback conditioning, workload push-forward, finite environmental certificate, and replay-specific empirical consequence.
3. **"ACT2 versus VERIFY was designed to make your method win."** Answer with independently authored controller corpus selected by syntax/executability, then classified by the locked theory.
4. **"You only distinguish operation names."** Answer with predeclared projection and parameter-sensitive action identity, including same-operation/different-variant cases.
5. **"Any 35/180 ms threshold would produce this."** Answer with preregistration, controls, boundary evidence, independent validation, and replicated real middleware; do not make threshold tuning part of the novelty claim.
6. **"R2 simply does 1.5x work because you programmed it to."** Answer that the result demonstrates the methodological consequence: different replay semantics benchmark different controller-induced workloads; native conservation proves the difference is real rather than measurement loss.

## 13. Lock condition before paper-wide drafting

The novelty/theory layer is considered locked when:

- the executable quotient and replay-validity APIs pass their exhaustive finite verification;
- action-identity granularity is explicit and regression-tested;
- the natural-controller inclusion policy is frozen before corpus outcomes are measured;
- at least one natural controller class exercises a distinction not reducible to ACT2-vs-VERIFY operation names;
- all related-work claims above are reflected in the paper's introduction/contributions, not buried only in Related Work.
