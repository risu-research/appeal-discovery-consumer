# ReplayMark Replay-Sufficiency Factorization

Status: **QUANTUM-JUMP NOVELTY GATE / NOT MANUSCRIPT-INTEGRATED**

This note asks the hardest novelty question after the exact `q_{C,H}` gate passed:

> Why is `claim + consequence horizon + target evidence + selective reuse` a ReplayMark methodological result rather than a loose bundle of known ideas?

The answer must survive strong prior art from trace replay, conformance testing, property-guided abstraction, predictive-state theory, off-policy evaluation, claim-relative evidence verification, and maximally permissive control.

The central conclusion is:

> **The individual mathematical ingredients are mostly established. The ReplayMark result is the typed factorization of a recorded-action replay decision into four distinct obligations whose outputs compose, together with exact sufficiency/maximality boundaries at their interfaces.**

Working name: **Replay-Sufficiency Factorization (RSF)**.

---

## 1. The object ReplayMark actually studies

A reactive benchmark replay is not merely a trace and not merely a target controller.

Fix:

- a recorded source action/trace `tau^S`;
- a target reactive controller/environment `T`;
- a benchmark claim `C`;
- a consequence endpoint/horizon `H_C` attached to that claim;
- target evidence `e` available at replay time; and
- a selective replay decision about the recorded projected action `z`.

RSF separates four questions that are commonly collapsed:

1. **Claim / semantic obligation — what distinctions does the benchmark claim care about?**
   `C -> phi_C`.
2. **Horizon / predictive obligation — what target history information is needed to preserve those distinctions for as long as the claim reaches?**
   `(T, phi_C, H_C) -> q_{C,H}`.
3. **Evidence / epistemic obligation — what does the retained target evidence actually establish about the relevant target state/action support?**
   `e -> Omega(e) -> S_C^-(e), S_C^+(e)`.
4. **Reuse / operational obligation — given that evidence, when may the recorded action be reused without making a support claim that fails in an admitted target world?**
   `(e,z) -> R*`.

The key point is **typed dependence**, not enumeration. The output of one stage defines the input language of the next:

`claim -> projected outputs -> claim-predictive quotient -> evidence image over quotient/worlds -> guaranteed/possible support -> maximal certified reuse`.

Changing `C` or `H` changes the state distinctions the evidence must resolve; changing `e` changes which recorded actions can be certified; `R*` is induced by that certification boundary rather than chosen heuristically.

---

## 2. Formal factorization

### 2.1 Claim semantics

Let

`phi_C : A -> Z_C`

be the benchmark-declared consequential projection. This remains normative: target dynamics do not silently rewrite the claim.

### 2.2 Consequence-horizon predictive state

For target histories `h,h'`, define

`h ==_{C,H} h'`

iff every admitted future input/feedback continuation of length at most `H` induces the same `phi_C`-projected target output prefix.

Let

`q_{C,H}(h) = [h]_{C,H}`.

For finite deterministic models this is the coarsest state partition sufficient to predict every claim-relevant output through `H`; the underlying minimization theorem is established automata/predictive-state theory and is not claimed as new.

### 2.3 Evidence image and support envelope

Evidence `e` leaves a nonempty compatible-history/world set `Omega(e)`.

Its image in claim-state space is

`Q_{C,H}(e) = { q_{C,H}(h) : h in Omega(e) }`.

For current support adjudication, every compatible world/history induces projected support `S_C(h)`.

Define

`S_C^-(e) = intersection_{h in Omega(e)} S_C(h)`

`S_C^+(e) = union_{h in Omega(e)} S_C(h)`.

Then current action `z` is exactly:

- certified valid iff `z in S^-`;
- certified invalid iff `z notin S^+`;
- unresolved otherwise.

Full identification of `q_{C,H}` is sufficient for all claim-predictions, but may be stronger than necessary to certify one particular recorded action. This strict separation between **predictive sufficiency** and **action-specific evidential sufficiency** is essential.

### 2.4 Operational closure

Define

`R*(e,z) = REUSE iff z in S_C^-(e)`.

For support validity, this is the maximally permissive sound current-step reuse rule available from `(e,z)`: reusing outside `S^-` is invalid in at least one target world still compatible with the same evidence.

`R*` is not claimed to be globally cost-optimal or distributionally faithful for stochastic controllers.

---

## 3. The strongest conceptual result: demand–evidence duality

RSF has two opposing refinement directions.

### Semantic demand grows

A finer claim projection or a longer consequence horizon can require more distinctions:

- claim refinement can split consequential classes;
- `H+1` can refine `q_{C,H}` into `q_{C,H+1}`.

The exact thermostat gate gave a strict empirical/model instance:

`|q_{C,0}| = 5 -> |q_{C,1}| = 14 -> |q_{C,2}| = 16`.

### Evidence uncertainty shrinks

Stronger evidence satisfies

`Omega(e') subseteq Omega(e)`.

Therefore

`S^-(e) subseteq S^-(e')`

and

`S^+(e') subseteq S^+(e)`.

The unresolved band can only shrink.

### Replay sufficiency is where these meet

A benchmark claim does not require “maximum fidelity.” It creates a **semantic demand**. Target evidence supplies **epistemic resolution**. Replay is certifiable exactly when the evidence is sufficient for the distinctions demanded by the claim at its horizon, or—more weakly for a specific action—when all still-compatible worlds agree on that action’s support.

This yields the central methodological principle:

> **Replay validity is a sufficiency relation between claim demand and target evidence, not a similarity relation between source and target traces.**

The trace is evidence/input to the problem, not the definition of fidelity.

---

## 4. Four-factor irredundancy: each omitted factor produces a different error

The factorization is not cosmetic. Each factor controls a failure mode that the other three cannot determine.

### 4.1 Omit the claim -> semantic category error

N2 gives the witness.

The same operation and target can be equal under an operation-only projection while `home` and `away` differ under the consequential preset claim. Target state, evidence, horizon, and replay mechanism can be held fixed while the correct validity judgment changes with `C`.

Therefore trace equality or target-policy equality cannot define replay fidelity without the benchmark claim.

### 4.2 Omit the horizon -> local equivalence masquerades as path equivalence

The pinned N2b model gives the witness.

At the current decision, `(presence=off,motion=off)` and `(off,on)` both select `away`; they are locally decision-equivalent. Under one admitted future `presence_toggle`, they yield `home` versus `comfort`.

Thus the same `C`, current action, and current target evidence can be sufficient for `H=0` and insufficient for `H=1`.

A feedback distinction is therefore not simply relevant or irrelevant; relevance is claim- and horizon-relative.

### 4.3 Omit the evidence -> semantic truth is confused with epistemic warrant

Let two target worlds remain possible under coarse evidence: one supports recorded action `z`, one excludes it.

The underlying target model and claim may be perfectly specified, yet the replay evaluator cannot soundly return a binary label from that evidence. After evidence refinement eliminates one world, the same action can become certified valid or certified invalid.

Thus `q_{C,H}` or a full target model does not by itself say what a concrete replay run is entitled to conclude from retained observations.

### 4.4 Omit reuse -> an audit has no canonical operational consequence

The support envelope can diagnose validity without defining a replay action.

- A policy that reuses outside `S^-` is unsound.
- A policy that never reuses is support-sound but strictly more conservative whenever `S^-` is nonempty.
- `R*` closes the methodology by identifying the unique maximal certified reuse set under the current evidence.

This factor is needed for **operational closure**, not to claim that replay is globally cost-optimal.

---

## 5. Why this is not just property-guided abstraction

Strong-preservation / generalized Paige–Tarjan work can compute coarsest abstractions preserving a language/property. Specification-guided Mealy abstraction can quotient outputs/states relative to a specification.

That prior art covers much of the `C,H -> q` substrate.

It does **not** by itself pose ReplayMark’s recorded-action problem:

- there is no source-recorded action whose reuse is under adjudication;
- no target-evidence object `e` leaving multiple live target conditions;
- no guaranteed/possible support envelope for that recorded action;
- no induced selective reuse boundary.

RSF therefore must cite property-guided abstraction as machinery and claim novelty only for the replay-specific composition and its exact interfaces.

---

## 6. Why this is not just causal states / PSRs / belief states

Causal states, epsilon-transducers, predictive state representations, and POMDP belief states formalize predictive/sufficient representations of history.

They support the idea that raw physical state need not be retained.

They do not answer:

- which output distinctions a benchmark claim licenses (`phi_C`);
- whether a historical source action is support-valid under the *current target controller*;
- whether retained evidence suffices to certify that specific action;
- whether the action may be reused rather than regenerated.

ReplayMark uses predictive-state theory to define the right target information object, then solves a different recorded-action/evidence problem on top of it.

---

## 7. Why this is not just ioco / trace conformance

ioco asks whether an implementation’s possible outputs after specification traces are contained in the specification’s possible outputs; simulation-based variants strengthen branching/context sensitivity.

This is close to the support/conformance side of ReplayMark and must be treated as serious prior art.

The difference is the measurement contract:

- ioco begins with an implementation/specification conformance relation;
- ReplayMark begins with a **historical source workload being reused as a benchmark on a changed target**;
- `phi_C` deliberately permits claim-relative coarsening that may differ across benchmark claims;
- `H` controls how much future controller behavior must remain relevant to the measurement;
- `e` formalizes incomplete target observations at the replay decision;
- `R*` decides whether to reuse the recorded source action itself.

ReplayMark is therefore not proposing a new generic conformance preorder; it is defining when a recorded benchmark action remains licensed for a particular target benchmark claim.

---

## 8. Why this is not just off-policy evaluation

Contextual-bandit/RL off-policy evaluation is the strongest statistical analogue because it combines:

- a logging behavior;
- a target policy;
- finite/infinite horizon;
- support/overlap requirements; and
- uncertainty about estimates.

This is an important reviewer attack and should be preempted.

But OPE’s object is **value estimation from logged data**. Its support condition asks whether target-policy occupancy/action probabilities are represented by the logging distribution sufficiently to identify/estimate expected reward.

ReplayMark’s object is **execution of a recorded source action/trace against a changed reactive target**. Its support condition is the reverse-facing operational question:

> is this recorded action one the target controller would admit under target feedback/state for the benchmark claim?

ReplayMark then uses the answer to decide reuse/regeneration on the live benchmark path. It does not estimate a target-policy value from importance weights and does not require the target policy to stay within the source logging support.

Thus OPE shares the vocabulary of policy, support, evidence, and horizon, but not the replay validity object or operational reuse relation.

---

## 9. Why this is not just maximally permissive control/shielding

Supervisory control and runtime shielding can synthesize maximally permissive safe action sets under a plant model and safety specification.

That is close to the maximality form of `R*`.

But their action set is chosen to keep the controlled system safe. ReplayMark’s binary choice is different: **reuse this historically recorded action or do not reuse it**, under incomplete evidence about the target condition, where “safe” means support-valid for the declared benchmark claim.

`R*` is therefore a theorem-induced reuse boundary for benchmark fidelity, not a new general safety-controller synthesis algorithm.

---

## 10. Why this is not just replay-with-feedback or modern trace replay

Replay-with-feedback in HPC directly establishes the practical premise that target performance can change future workload generation; its 2024 implementation modifies submission timing through feedback dependencies.

ReplayMark’s E3b result is deliberately stronger/different: timing-reactive replay can still preserve the wrong semantic action, so feedback sensitivity alone is not a validity criterion.

Modern agent trace replay makes the claim-dependence visible in practice. NVIDIA Dynamo explicitly replays the **serving workload rather than the agent itself**: model decisions and tools are not re-executed. That is perfectly sensible for a serving-infrastructure claim, but it would not by itself establish live-agent behavioral fidelity.

RSF turns this informal scope distinction into a general contract: fidelity is relative to what the benchmark claims, how far consequences extend, and what target evidence supports.

---

## 11. Adjacent 2026 claim-relative evidence work: serious but different

Recent work such as *What Does an Evaluation License?* and *ClaimReceipt* makes claim-relative evidence sufficiency explicit for evaluation artifacts. That strengthens, rather than removes, the need to draw ReplayMark’s novelty line carefully.

Those methods ask whether retained evidence licenses recomputation/inference of evaluation claims, often returning typed stops or inconclusive outcomes.

ReplayMark’s distinct object is a **reactive controller generating the benchmark workload itself**. Its chain contains objects absent from those claim-audit methods:

- target controller support conditioned on live target feedback/state;
- consequence-horizon predictive state `q_{C,H}`;
- a recorded source action whose semantic admissibility can differ from the target-generated action;
- a theorem-induced maximal reuse/regeneration boundary.

So ReplayMark should not claim ownership of “claim-relative evidence sufficiency” in general. It should claim a specific reactive-replay factorization.

---

## 12. The strongest genuinely ReplayMark-specific theorem package

The paper should not market one giant theorem. The scientifically defensible package is a chain of established-substrate + new-interface results.

### Result F1 — claim/horizon factorization

For a declared benchmark claim and consequence horizon, the target’s relevant state is the claim-predictive quotient `q_{C,H}` rather than raw state identity. Current decision equivalence is the horizon-zero fixed-state slice.

Underlying minimization mathematics: prior art.

Replay-specific role: determines the target information demanded by a historical replay claim.

### Result F2 — exact evidence boundary

Given retained target evidence, `S^- / S^+` is the maximally informative sound three-valued support adjudicator for a recorded projected action.

Replay-specific role: separates semantic validity from what the replay run can actually establish.

### Result F3 — maximal certified reuse

`R*` reuses iff the recorded action is in guaranteed support and is maximally permissive among support-sound policies using the same evidence.

Replay-specific role: converts validity into an operational replay/regenerate boundary.

### Result F4 — factor irredundancy

N2, N2b/full thermostat, incomplete-evidence countermodels, and `R*` maximality show that claim, horizon, evidence, and reuse solve distinct obligations and cannot be collapsed into one generic “fidelity” knob.

This irredundancy is what makes the composition methodological rather than cosmetic.

---

## 13. The minimal-information theorem story

RSF creates three different optimality notions that should never be conflated:

1. **Predictive minimality** — `q_{C,H}` is the coarsest state sufficient for *all* claim-relevant outputs through the horizon.
2. **Evidential minimality / exact sufficiency boundary** — a specific action can be certified without reconstructing the whole predictive state whenever all evidence-compatible worlds agree on its support.
3. **Operational maximality** — `R*` reuses on every evidence/action pair that any support-sound fixed-evidence policy can reuse.

This gives a striking “minimum–minimum–maximum” structure:

> **minimum claim state, no more evidence than the action requires, maximum certified reuse.**

No generic replay rule like “preserve the trace,” “match raw feedback,” or “always rerun the controller” achieves all three.

---

## 14. Horizon must be claim-bound, not tuned

`H` is a potential reviewer attack if presented as a free hyperparameter.

The correct methodological contract is that the benchmark endpoint declares or induces the consequence horizon before replay analysis.

Examples:

- current action correctness: `H=0`;
- next closed-loop decision: `H=1`;
- task/batch workload claim: horizon extends to the task/batch terminal decision boundary;
- unbounded streaming behavior: use a stabilized/infinite-horizon quotient or explicitly bound the claim.

Where possible, the horizon can be derived by ordinary dependency/cone-of-influence reasoning from the measured endpoint. This derivation machinery is prior art; ReplayMark’s point is simply that consequence horizon belongs to the benchmark contract and must not be chosen after observing a favorable split.

---

## 15. Empirical alignment: why the factorization earns space in this paper

The current evidence already instantiates every interface.

### Claim

N2 shows operation identity can be too coarse for a consequential preset claim; N2b shows raw feedback identity can be too fine for the current decision.

### Horizon

The exact full-model gate gives:

- E3b: 6 raw decision conditions -> 3 stable claim states at `H=0`; no artificial horizon effect.
- Better Thermostat: `5 -> 14 -> 16` classes over `H=0,1,2`, stabilizing at two future triggers.
- N2b shortest distinguishing continuation: one presence toggle.
- automatically discovered shortest depth-2 witness: presence toggle then night toggle.

### Evidence

The support envelope formalizes supplied-state / observed-prefix / model-prefix sufficiency and returns valid / invalid / unresolved without guessing.

### Reuse

`R*` formally separates safe reuse, definite regeneration, and evidence-refine-or-regenerate.

### Downstream consequence

E3b then ties semantic mismatch to real target workload and provisioning/capacity conclusions, including 512 vs 768 explicit queue capacity and 250 vs 166 tasks under Mosquitto’s documented default queue policy.

This matters for novelty: the factorization is not a detached theoretical appendix; each layer already has a concrete role in the existing falsification chain.

---

## 16. Prior-art matrix

| Literature | Claim-relative semantics | Horizon/predictive state | Incomplete evidence | Recorded-action support | Selective reuse | Benchmark-conclusion validation |
|---|---:|---:|---:|---:|---:|---:|
| Classical trace replay | usually fixed trace fields | timing/context, not claim quotient | rarely formal | source trace assumed workload | replay by construction | performance metrics |
| Replay with Feedback | fixed workload semantics | dependency/timing feedback | no exact evidence envelope | semantic jobs retained | timing adaptation | scheduler/infrastructure metrics |
| Strong preservation / spec-guided abstraction | yes, property/spec | yes | assumes model/abstraction, not live evidence | no historical source action | no | verification result |
| Causal states / PSR | output/process dependent | yes, central | statistical/model uncertainty separate | no | no | prediction/control |
| ioco / conformance testing | specification-defined | traces/branching | model uncertainty not ReplayMark envelope | implementation outputs, not source-trace reuse | no | conformance verdict |
| Off-policy evaluation | target value/reward defines estimand | yes | statistical uncertainty/overlap | logging-vs-target support | no live source-action reuse | estimated target value |
| Shielding / supervisory control | safety/property | yes | usually model state/belief | no historical trace obligation | maximally permissive action control | safety/reachability |
| Claim-replay / ClaimReceipt | yes | not reactive consequence quotient | yes, central | no live target-controller action support | no | claim/evidence audit |
| **ReplayMark RSF** | **benchmark projection** | **claim-predictive `q_{C,H}`** | **compatible-world support envelope** | **yes: recorded action vs target support** | **maximal certified reuse `R*`** | **real workload/capacity flips** |

The novelty claim should be about the last-row composition, not uniqueness of any isolated column.

---

## 17. What we can and cannot responsibly say about novelty

A literature search cannot prove global absence of prior work.

The defensible statement is:

> **Across the trace-replay, reactive-workload, conformance-testing, property-guided abstraction, predictive-state, off-policy-evaluation, and claim-evidence literatures reviewed here, we did not find a prior methodology that jointly (i) makes replay validity benchmark-claim relative, (ii) derives the minimal target state required over the claim’s consequence horizon, (iii) adjudicates a recorded action under incomplete target evidence by guaranteed/possible target-controller support, and (iv) turns that evidence boundary into a maximally permissive sound reuse rule.**

That statement is strong enough if the related-work section demonstrates the boundaries rather than pretending the components are individually novel.

---

## 18. Reviewer-grade attacks and required answers

### “This is just Mealy minimization.”

Answer: minimization supplies `q`; it does not define the recorded-action/evidence/reuse problem. Cite it as substrate.

### “This is just ioco.”

Answer: ioco is a generic implementation/spec conformance relation. ReplayMark binds conformance to a benchmark claim and a historical source action, under incomplete target evidence, then decides reuse.

### “This is just off-policy support.”

Answer: OPE estimates target-policy value from behavior-policy logs. ReplayMark asks whether a source-recorded action may be executed as target workload under target feedback; target support, not logging support, is the admissibility object.

### “Claim-relative evidence is already known.”

Answer: agree. ReplayMark does not claim generic claim-evidence theory. Its novelty is reactive workload generation plus consequence horizon plus action reuse.

### “Why not always regenerate from the target controller?”

Answer: that is sound but destroys the point of selective replay and may be unnecessarily expensive; `R*` proves exactly when reuse is already certified. No cost-optimality claim is needed.

### “Why not just require exact state/feedback?”

Answer: the full thermostat quotient proves exact raw state is overkill: 32 frozen relevant states compress to 16 claim states, while current-decision equality is simultaneously too coarse for 28 pairs and too fine for 24 others.

### “Why is H not researcher degrees of freedom?”

Answer: bind it to the benchmark endpoint before analysis; if the endpoint is unbounded, say so and use the stabilized/infinite-horizon object.

---

## 19. Manuscript-level intellectual spine if this gate is promoted

The strongest compact story is not “we add predictive state theory.”

It is:

> A trace does not define its own fidelity. A benchmark claim determines which action distinctions matter; its consequence horizon determines which target-history distinctions can affect those actions; retained evidence determines which target conditions remain possible; and only actions supported across all those conditions may be safely reused. ReplayMark therefore factorizes replay fidelity into semantic demand, predictive state, epistemic sufficiency, and certified reuse.

Then the memorable compression:

> **Replay the claim state, not the trace. Reuse only what the evidence certifies.**

And the deepest methodological statement:

> **Replay validity is not maximum similarity. It is minimum sufficient information for the claim, followed by maximum certified reuse.**

---

## 20. Promotion verdict

**PROMOTE as a serious quantum-jump candidate, with a narrow novelty line.**

Reasons:

1. The full-model gate already showed `q_{C,H}` is non-decorative: E3b stabilizes at H=0 while Better Thermostat exhibits exact depth-1/depth-2 consequences and 2x raw-state compression.
2. The support envelope and `R*` provide exact epistemic and operational boundaries rather than heuristic glue.
3. The four factors are empirically/theoretically irredundant in the current corpus.
4. Strong prior art actually improves the positioning: ReplayMark can borrow mature minimization/conformance concepts and spend novelty budget on the replay-specific interfaces and downstream benchmark consequence.

**Do not yet rewrite the manuscript solely from this note.** One final gate should test whether this factorization can replace—not add to—the current formalism in <= roughly 0.35 net page and whether the three frozen contributions can absorb it without becoming a fourth contribution. If it cannot be compressed, the intellectual result may still be real but inappropriate for the current 9-page PerCom paper.

---

## 21. Literature anchors used for the novelty boundary

- Ranzato & Tapparo, *Generalizing the Paige–Tarjan algorithm by abstract interpretation*, Information and Computation 206(5), 2008 — coarsest refinements / strong preservation.
- Matsumoto et al., *Efficient Black-Box Checking with Specification-Guided Abstraction*, ACM TECS 24(5s), 2025 — specification-guided output/state abstraction for Mealy machines.
- Causal-state / epsilon-transducer and predictive-state literature — minimal sufficient predictive representations of histories/input-output processes.
- Tretmans/ioco and later ioco-simulation work — output support after traces and branching conformance.
- Li, Chu, Langford & Wang, WSDM 2011 — data-driven contextual-bandit replay for unbiased off-policy evaluation; later finite-horizon OPE literature makes support/overlap and horizon explicit.
- Maximally permissive supervisory-control literature — maximal action permission under a specification.
- Madon et al., *Replay with Feedback*, FGCS 155, 2024 — workload replay where target performance changes later submission timing.
- NVIDIA Dynamo Agent Trace Replay documentation — serving-workload replay explicitly does not rerun agent decisions/tools, illustrating practical claim scoping.
- *What Does an Evaluation License?* (arXiv:2608.19269, 2026) and *ClaimReceipt* (arXiv:2609.01992, 2026) — recent claim-relative evidence/claim-replay work; adjacent but not reactive target-controller replay/reuse.
