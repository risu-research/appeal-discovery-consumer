# ReplayMark quantum-jump research synthesis: minimal claim-predictive replay state

Status: **RESEARCH GATE / NOT MANUSCRIPT-INTEGRATED**

This note is the result of a literature-driven attack on the post-v31 theory direction. It deliberately separates (i) what existing theory already gives us, (ii) what ReplayMark can legitimately reuse, and (iii) what would have to be genuinely replay-specific to justify reopening the manuscript.

## 1. Bottom-line change of direction

The previous candidate, `phi_C -> phi_C^dagger` by automatically refining the benchmark action projection until it is continuation-stable, is **not the best quantum-jump target**.

The reason is conceptual, not merely novelty-related: `phi_C` says what the benchmark claim *cares about*. That is a normative measurement choice. Target dynamics alone cannot generally infer that choice without risking a silent change of claim. If a benchmark truly claims only operation-count fidelity, forcing it to distinguish `home` from `away` because those actions can have different futures changes the benchmark semantics rather than merely making the replay more sound.

The stronger and cleaner factorization is:

1. `phi_C` remains the benchmark-declared output/consequence semantics.
2. The target controller induces the **minimal predictive state needed to reproduce those claim-relevant outputs over a declared consequence horizon H**.
3. Evidence is judged by how much uncertainty it leaves over that claim state and, more weakly, whether it still suffices to certify the particular recorded action through the existing support envelope.
4. `R*` remains the maximal support-sound reuse rule under the available evidence.

Working name: **claim-predictive replay state**. Optional diagnostic quantity: **consequence depth**.

The intellectual pipeline becomes:

`claim semantics -> minimal claim-predictive state -> evidence sufficiency -> safe selective reuse -> benchmark consequence`.

This is a better-founded category change than automatic action-projection closure.

---

## 2. Literature result: the mathematical ingredients are established

### 2.1 Mealy/Nerode minimization

For deterministic reactive systems, states that produce identical outputs under every future input continuation are behaviorally equivalent. Minimal Mealy realizations are unique up to isomorphism. Active automata-learning work uses exactly this continuation-based state distinguishability and returns distinguishing suffixes/counterexamples.

Implication for ReplayMark: **do not claim invention of a minimal continuation quotient**. We can borrow it.

### 2.2 Stochastic trace equivalence

Recent stochastic Mealy-machine learning defines two traces as equivalent when *every continuation sequence* induces equal future output distributions. This is a direct stochastic analogue of Nerode equivalence.

Implication: a law-preserving ReplayMark analogue has a clean established substrate. The current support-only paper should remain weaker unless full stochastic-law evidence is identified.

### 2.3 Causal states and epsilon-transducers

Computational mechanics defines causal states as equivalence classes of histories with identical conditional future distributions; they are minimal sufficient predictive statistics. Epsilon-transducers extend this idea to input-output processes.

Implication: the slogan “retain only the history needed to predict claim-relevant future controller behavior” has serious theoretical support. Again, the general minimal-predictor theorem is not new.

### 2.4 Predictive state representations / information states

Predictive state representations encode controlled-system state through predictions of future tests. Information-state theory similarly seeks a history statistic sufficient for downstream prediction/control.

Implication: full physical/system state is not privileged. A replay methodology can legitimately ask for a claim-sufficient predictive state instead.

### 2.5 Property/specification-guided abstraction

Ranzato/Tapparo-style generalized Paige-Tarjan and complete-shell work computes coarsest/minimal refinements that strongly preserve a chosen specification language. More importantly for novelty risk, Matsumoto et al. (EMSOFT/TECS 2025) already introduce **specification-guided abstraction of Mealy machines**, including compatible output abstractions and a canonical induced state equivalence, then directly learn the abstract machine for black-box checking.

Implication: “compute a canonical property-specific abstraction” is emphatically **not** sufficient novelty for ReplayMark. This literature is the strongest reason to reject the previous `phi_C^dagger` direction as the headline jump.

### 2.6 Minimal observation / sensor activation

Discrete-event-systems literature contains minimal sensor/event-observation policies preserving detectability, diagnosability, or observability.

Implication: “observe the minimum information needed for a property” is also established in generic form. ReplayMark’s evidence contribution must stay tied to its source-recorded action / target-controller support relation, not claim generic sensor minimization.

### 2.7 Replay-specific prior work remains narrower

Replay-with-feedback work in HPC explicitly argues that infrastructure performance can alter future user submission behavior and therefore rigid historical replay can become unrealistic. Contemporary agent-serving trace replay explicitly freezes agent decisions/tools when replaying serving workload. These systems make the practical replay problem more timely, but they do not provide ReplayMark’s claim-relative target-support/evidence criterion.

---

## 3. Formal object: claim-predictive replay state

Fix:

- a target reactive controller/environment model;
- a benchmark claim projection `phi_C` over controller actions/outputs;
- an admitted future feedback/input alphabet and model;
- a finite consequence horizon `H` measured in future controller decision points.

For target histories `h,h'`, define

`h ==_{C,H} h'`

iff for every admitted future feedback/input word `u` of length at most `H`, the target produces the same `phi_C`-projected output prefix from `h` and `h'` under `u`.

Let

`q_{C,H}(h) = [h]_{C,H}`

be the induced quotient state.

### Proposition Q1 — finite-horizon predictive sufficiency

`q_{C,H}` is sufficient to determine every claim-projected target output prefix for every admitted continuation of length at most `H`.

### Proposition Q2 — minimality

Let `eta(h)` be any history statistic sufficient for those same predictions. Then

`eta(h)=eta(h') => q_{C,H}(h)=q_{C,H}(h')`.

Thus `q_{C,H}` is the unique coarsest such predictive partition, up to relabeling.

This is a replay specialization of standard minimal-state/minimal-sufficient-statistic results, not new automata theory.

### Proposition Q3 — horizon monotonicity

`==_{C,H+1}` refines `==_{C,H}`.

More future claim behavior can force distinctions that are irrelevant to an immediate decision.

### Proposition Q4 — distinguishing continuation

If `q_{C,H}(h) != q_{C,H}(h')`, there exists an admitted feedback/input suffix of length at most `H` that produces different claim-projected behavior. A shortest such suffix is a constructive witness.

Define its length as the **consequence depth** between the two histories for claim `C` (bounded by `H`). This is a replay interpretation of classical distinguishing sequences / bounded behavioral equivalence; the underlying mathematics is established.

### Infinite horizon

For a finite deterministic controller, refinement stabilizes at the ordinary minimal claim-projected reactive machine. For stochastic controllers, equality can be lifted from output words to future projected output laws, matching stochastic Mealy trace equivalence / epsilon-transducer ideas. For ReplayMark’s support-level claims, a support-language analogue is the conservative fit.

---

## 4. Crucial separation from the old `phi_C^dagger` proposal

The two constructions answer different questions.

- `phi_C`: **What consequences does the benchmark claim distinguish?** Normative; declared by the benchmark.
- `q_{C,H}`: **What target history/state information is minimally needed to predict those consequences over horizon H?** Derived from the controller/environment model.

This avoids a category error. We do not let target dynamics silently rewrite the measurement claim.

It also produces a more useful statement:

> The right replay state is not the raw system state and not the raw feedback. It is the minimal target history statistic that predicts the benchmark’s consequential future over the claim horizon.

---

## 5. Exact external-controller witness already inside the current evidence

Pinned external controller:

`n3roGit/MyHomeAssistantMods@57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f`
`BetterThermostat_RoomHeatControl_Lean.yaml`.

Its exact priority logic is:

`boost > sleep/night > away/no-presence > eco > activity > comfort/motion > home`.

The current N2b pair is:

- `h_A`: presence off, motion off; higher-priority flags inactive;
- `h_B`: presence off, motion on; higher-priority flags inactive.

Both select `away` now because absence outranks motion. That is the existing safe-side result.

But the pinned controller gives a stronger exact semantic fact without a new experiment:

- apply one future presence-on event while preserving the respective motion value;
- from `h_A`, target preset becomes `home`;
- from `h_B`, target preset becomes `comfort`.

Therefore these two raw feedback states are **equivalent for the current decision but not for one-step predictive behavior**.

This is precisely what the horizon-indexed quotient is supposed to expose:

`q_{C,0}(h_A) = q_{C,0}(h_B)` but `q_{C,1}(h_A) != q_{C,1}(h_B)`

under the natural preset-action claim projection and the presence-update transition slice.

This materially sharpens the current N2b interpretation. “Raw feedback difference can be irrelevant” remains true for the current decision; “irrelevant forever” would be false.

---

## 6. Exact finite-state sanity check on the pinned N2/N2b slice

Restrict the pinned controller to the two actually varied feedback bits with `boost=night=eco=activity=false`:

- `(presence=0,motion=0) -> away`
- `(0,1) -> away`
- `(1,0) -> home`
- `(1,1) -> comfort`.

Use actual presence/motion state-change events as the finite input alphabet. Exact partition refinement gives:

- immediate/output horizon: 3 classes, with `(0,0)` and `(0,1)` merged;
- one future decision point: 4 classes; the N2b pair splits;
- further horizons do not refine this four-state slice.

The shortest distinguishing input for the N2b pair is `presence := on`, producing `home` versus `comfort`.

This is a semantic model check of the pinned priority logic, not a new runtime experiment and not evidence of prevalence.

---

## 7. How this would interact with the existing support envelope

The support envelope should **not** be replaced.

`q_{C,H}` answers a universal predictive-state question: what state information suffices to predict all claim-relevant behavior through horizon H?

The existing envelope answers a weaker action-specific epistemic question: given current evidence `e`, is this particular recorded projected action guaranteed supported, guaranteed excluded, or unresolved?

These layers should remain distinct because a particular action may be certifiable even when evidence does not identify a unique predictive claim state.

This yields a clean hierarchy:

1. **Claim semantics** — `phi_C`.
2. **Predictive state** — `q_{C,H}`.
3. **Evidence uncertainty** — compatible target histories / claim states.
4. **Action adjudication** — `S_C^-`, `S_C^+`.
5. **Reuse** — `R*`.

That is more principled than demanding full state reconstruction.

---

## 8. Replay-specific refinement: obligation state (promising, not yet promoted)

A full claim-predictive state may still retain behavior irrelevant to one recorded trace. ReplayMark can potentially go one step further.

For a fixed remaining recorded source suffix `tau`, define the **replay obligation semantics** of a target history as the set/law of future feedback words under which that source suffix remains target-supported at the declared projection. Histories are obligation-equivalent if these validity outcomes agree for every admitted continuation through horizon H.

The quotient would be the minimal state needed to audit **this replay obligation**, not to model all target outputs.

This is more ReplayMark-specific than generic Mealy minimization or specification-guided abstraction, but it is not promoted yet because:

- it needs a clean treatment of regeneration after the first invalid source action;
- it may collapse into ordinary property-specific automata abstraction once formalized;
- current experiments are mostly stepwise and should not be overclaimed as validating a full obligation automaton.

Keep as a possible second-stage refinement only if the broader claim-state gate passes.

---

## 9. Novelty line after the literature review

### Not novel / must be cited as substrate

- Nerode/Mealy state minimization.
- distinguishing suffixes and active automata learning.
- causal states / epsilon-transducers.
- predictive state representations.
- bisimulation/simulation and bounded behavioral equivalence.
- complete-shell / generalized Paige-Tarjan property-preserving refinement.
- generic specification-guided Mealy abstraction.
- generic minimal sensor/observation selection.

### Plausible ReplayMark novelty

A replay-specific **measurement contract** that composes these established ingredients around a recorded workload:

`benchmark claim projection + target-generated claim-predictive state + evidence-conditioned support envelope + maximal sound reuse`,

and shows experimentally that crossing the resulting semantic boundary changes real provisioning/capacity conclusions.

The strongest claim is methodological, not “new automata theory”:

> Replay fidelity needs neither full trace identity nor full target-state reconstruction. For a declared claim horizon, it needs enough target information to preserve the controller’s claim-predictive state—or, for a particular recorded action, enough evidence to certify support despite residual state uncertainty.

---

## 10. Why this could be a real quantum jump

It would close two opposite arbitrariness problems at once.

Current v31 already says:

- raw feedback equality is too strong;
- operation equality can be too weak.

The new theory adds:

- **full state/history is also too strong**;
- **current-decision equality can be too weak for a future-horizon claim**.

And it gives a canonical answer between them: the minimal claim-predictive state for horizon H.

The paper’s remembered thesis could become:

> **Replay the claim state, not the trace.**

More formally:

> Replay fidelity requires neither maximal semantic detail nor maximal environmental observation. It requires the benchmark’s declared consequential semantics, the minimal target state that predicts those consequences over the claim horizon, and enough evidence to certify the recorded action under that state uncertainty.

If stated compactly, this changes ReplayMark from a pointwise replay audit into a **minimal-information theory of reactive replay** while preserving the existing empirical core.

---

## 11. Quantum-jump gate — hard kill criteria

Do not reopen v31 unless all of the following pass.

1. **External-controller nontriviality.** The pinned N2/N2b controller must yield an automatically derived merge at current horizon and split at the next horizon, with a mechanically generated distinguishing suffix.
2. **No claim rewriting.** `phi_C` stays normative; the theory derives target state, not benchmark meaning.
3. **Prior-art separation.** The contribution must be stated as replay-specific claim/evidence/reuse composition, explicitly crediting property-guided abstraction and predictive-state theory.
4. **Compression.** Main-paper addition replaces existing decision-equivalence/evidence prose and costs at most ~0.25–0.35 page net.
5. **Empirical compatibility.** Existing N2/N2b/E3/D1/D2 evidence becomes more coherent; no new empirical claim is required.
6. **Constructive artifact.** A finite-state checker can compute `q_{C,H}` and a shortest distinguishing suffix on at least the pinned thermostat slice and one frozen constructed controller.
7. **No fake universality.** Stochastic full-law, continuous-state, black-box-learning, and arbitrary-environment extensions remain explicitly separate unless actually implemented.

If these fail, keep v31. If they pass, this is the first post-v31 direction with a credible category-changing payoff.

---

## 12. Research anchors

- Ranzato & Tapparo, *Generalizing the Paige–Tarjan algorithm by abstract interpretation*, Information and Computation 206(5), 2008, DOI 10.1016/j.ic.2008.01.001.
- Ganty, Manini, Ranzato, *Reachability-Guided Abstraction Refinement*, FM 2026 — forward completeness / complete shells and relevance-guided precision.
- Matsumoto, Watanabe, Suenaga, Waga, *Efficient Black-Box Checking with Specification-Guided Abstraction*, ACM TECS 24(5s), 2025, DOI 10.1145/3762659.
- Tappler et al., *Active model learning of stochastic reactive systems*, Software and Systems Modeling, 2024 — continuation-based stochastic trace equivalence.
- Barnett & Crutchfield, *Computational Mechanics of Input–Output Processes: Structured Transformations and the ε-Transducer*, J. Stat. Phys., 2015, DOI 10.1007/s10955-015-1327-5.
- Littman & Sutton, *Predictive Representations of State*, NeurIPS 2001.
- Isberner & Steffen, *An Abstract Framework for Counterexample Analysis in Active Automata Learning*, ICGI/PMLR 2014.
- Wang et al., *Optimal sensor activation for diagnosing discrete event systems*, Automatica 46(7), 2010.
- Gyulai et al., *Replay with Feedback: How does the performance of HPC system impact user submission behavior?*, FGCS 155, 2024.

