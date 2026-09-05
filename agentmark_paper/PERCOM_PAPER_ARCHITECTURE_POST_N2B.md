# AgentMark — PerCom 2027 Paper Architecture After N2b

Status: **paper-engineering working lock after empirical stop rule**.

Official PerCom 2027 constraints checked 2026-09-05:

- at most **9 pages technical content** in 10pt two-column format;
- up to **1 additional references-only page**;
- double-blind review;
- paper registration: **2026-09-11 AoE**;
- paper submission: **2026-09-18 AoE**;
- external links that reveal author identity can cause desk rejection;
- accepted papers may submit an artifact, and artifact presence is considered among Best Paper criteria.

Official source: `https://percom.org/call-for-papers/`.

The architecture below therefore optimizes for reviewer comprehension and claim density, not for documenting every experiment ever run.

## 1. Working title

Preferred working title:

> **AgentMark: Controller-Semantic Validity for Replay in Reactive Pervasive Systems**

Why this title:

- states the new object (`controller-semantic validity`) rather than falsely claiming feedback-aware replay;
- makes replay/benchmarking explicit;
- establishes PerCom scope in the title through reactive pervasive systems;
- does not overclaim universal whole-trace or physical-device validity.

Possible sharper title to reconsider only after the first full draft:

> **When Timing-Aware Replay Replays the Wrong Action**

This is memorable but less self-contained and less venue-scoped; use only if the abstract immediately supplies the formal object and pervasive-systems context.

## 2. One-sentence paper thesis

> **A replay can adapt to target timing and still benchmark an action that the target-conditioned live controller would not issue; replay validity therefore has to be evaluated at a declared controller-semantic action projection, with feedback changes quotiented by the decisions they actually induce.**

Every section, figure, theorem, and experiment must pay rent against this sentence.

## 3. Exactly three contributions

The introduction should converge to only these three contributions.

### Contribution 1 — Replay-validity object

A projection-explicit, target-conditioned **controller-semantic replay-admissibility criterion** based on the live controller kernel, plus a decision-equivalence quotient that distinguishes behaviorally relevant feedback shifts from irrelevant raw feedback changes.

Do not claim support inclusion, trace inclusion, TV contraction, or feedback awareness as individually novel.

### Contribution 2 — Executable methodology and certificate

**AgentMark**, an executable methodology that applies the same validity object to rigid, timing-aware, or semantic/closed-loop replay mechanisms; checks local/prefix-conditioned support at a declared action granularity; and connects observed feedback-law shift to workload-level shift with a finite-sample SAFE / UNSAFE / UNRESOLVED certificate under stated sampling assumptions.

The mechanism taxonomy is instrumentation for the criterion, not the novelty by itself.

### Contribution 3 — Prediction-driven systems evidence

Replicated native evidence showing complementary separations:

1. **timing-aware but semantically unsupported** replay in Mosquitto, native Home Assistant, and an official HA controller;
2. **same operation, different consequential action** in an independently authored thermostat controller (`TV_operation=0`, `TV_action=1`);
3. **different raw feedback, same consequential action** in that external controller (`TV_feedback=1`, quotient/action TV=0), where replay remains supported;
4. target-conditioned semantics can change the native workload itself by an exact **1.5x** in both Mosquitto and HA middleware experiments.

This empirical structure matters more than the number of experiments.

## 4. Nine-page budget

Target **8.7–8.8 pages** in the first compact draft, leaving ~0.2 page emergency margin. Do not plan to use an appendix; appendices count against the technical page limit.

| Section | Target pages | Purpose |
|---|---:|---|
| Abstract + title footprint | 0.30 | Problem, gap, method, strongest results, scope |
| 1. Introduction | 1.05 | Pervasive replay problem -> timing/semantic separation -> 3 contributions |
| 2. Controller-Semantic Replay Validity | 1.35 | Kernel, projections, support criterion, quotient, exact deterministic result, stochastic bound/certificate |
| 3. AgentMark Methodology | 1.00 | R0/R1/R2 as evaluated mechanisms, alignment, certificate, fail-closed trace handling |
| 4. Experimental Design | 1.05 | Substrates, natural-controller selection, provenance, replication, exact vs statistical outcomes |
| 5. Results | 2.25 | Mechanism separation + natural semantic separation + workload consequence |
| 6. Related Work | 0.85 | Closest replay work first; conformance/OPE second |
| 7. Scope, Limitations, Implications | 0.55 | Explicit nonclaims; when benchmark conclusions can be invalidated |
| 8. Conclusion | 0.20 | One thesis, no new claims |
| **Buffer** | **0.40** | Caption/format variance and reviewer-readable spacing |

If the draft exceeds nine pages, cut experiments/details before cutting definitions necessary to understand the claim.

## 5. Narrative order — prediction, not chronology

Do **not** tell the project history in the paper. The reader should never need to know that E3b preceded E3c or that N2 required an observer correction.

Use this logic:

1. Reactive pervasive benchmarks often replay recorded action traces.
2. Existing work correctly shows that closed-loop feedback can matter.
3. Missing methodological question: **when is the recorded action itself still a valid surrogate for what the target-conditioned controller would do?**
4. Define validity at a declared projection.
5. Derive two opposite predictions:
   - crossing a decision class can make a recorded action unsupported;
   - changing raw feedback within one decision class must *not* be treated as workload change.
6. Test both predictions on real middleware and independently authored controllers.
7. Show the benchmark consequence: different replay semantics can benchmark different native workloads.

This makes E3b/E3c/N1/N2/N2b look like consequences of one model rather than five unrelated case studies.

## 6. Introduction blueprint

### Paragraph 1 — pervasive-systems stakes

Start with reactive pervasive systems: smart environments, sensor-driven automation, edge services, and middleware evaluate behavior using recorded/replayed workloads. Replay is attractive because it appears to hold the workload fixed while the target environment changes.

### Paragraph 2 — the hidden assumption

Expose the assumption: a recorded action remains the action the current live controller would produce under target feedback. A timing-aware replay can react to target completion yet preserve the wrong semantic action.

Use one concrete two-step teaser, not a survey.

### Paragraph 3 — why existing closed-loop replay does not settle the methodological question

Acknowledge directly that prior systems already preserve/adapt feedback loops. Then distinguish AgentMark: it evaluates whether a replay workload is **controller-semantically admissible**, independent of whether the replay mechanism is rigid, timing-aware, or domain-specific closed-loop.

### Paragraph 4 — formal intuition

Introduce declared action projection and controller support. Raw feedback difference is insufficient; feedback matters only through the controller decision class it induces.

### Paragraph 5 — strongest evidence

In one compact paragraph:

- R1 adapts timing yet is unsupported in E3b/E3c/N1;
- N2 proves operation identity can hide action change;
- N2b proves raw feedback change can be behaviorally irrelevant;
- E3b/E3c show exact 1.5x native workload difference under target-conditioned semantic replay.

### Paragraph 6 — three contributions

Exactly the three contributions in Section 3 above.

## 7. Formal section — minimum sufficient mathematics

### 7.1 Controller kernel and declared projection

At aligned controller state `s`, define projected controller kernel:

`K_s^phi(e | y)`

where `y` is observed feedback and `phi` declares what counts as the action being evaluated.

Paper-facing projections:

- `operation`;
- `action = (operation, target class, adapter-declared semantic variant)`.

Legacy/internal projections need not appear in the main paper unless required to reproduce a figure.

### 7.2 Local target admissibility

For source-recorded `e`:

`K_s^phi(e|y_S) > 0`

but replay failure under target feedback occurs if:

`K_s^phi(e|y_T) = 0`.

State clearly that this is local / prefix-conditioned. Do not imply a whole-trace theorem unless target state is tracked along the target-conditioned prefix.

### 7.3 Decision-equivalence quotient

`y ~_(s,phi) y'` iff `K_s^phi(.|y) = K_s^phi(.|y')`.

For deterministic projected controllers, workload shift is exactly the TV distance after pushing feedback laws through the decision class. This is the conceptual bridge to both N2 and N2b.

### 7.4 Stochastic sensitivity and finite-sample certificate

Give the Dobrushin-style sensitivity and contraction in compact form. Label the inequality as classical; contribution is its use inside the replay-validity methodology.

Give SAFE / UNSAFE / UNRESOLVED in a small boxed definition or three-line equation. State the temporal/IID-style assumptions required by the chosen multinomial concentration radius.

Do not spend half a page proving classical probability.

## 8. Replace the strict 'Semantic Fidelity Ladder'

Use **Replay Fidelity Obligations** or **Replay Validity Dimensions**.

Recommended sequence for a figure/text callout:

1. timing relation;
2. operation identity;
3. action identity;
4. controller admissibility under target feedback;
5. induced path/workload.

Do not assert these form a universal total order. Timing is partly orthogonal to semantic identity; admissibility is a predicate at an aligned target decision point; path/multiplicity is trace-level.

Empirical separators make the structure concrete:

- timing adaptation !-> controller admissibility: E3b/E3c/N1;
- operation identity !-> action identity: N2;
- raw feedback inequality !-> semantic inequality: N2b;
- frozen sequence !-> target-induced workload equality: E3b/E3c R1 vs R2.

## 9. Figure/table budget

Use **two figures + two tables maximum** unless the draft proves more visual space is justified.

### Figure 1 — Teaser / validity failure

One reactive-controller decision with source vs target feedback:

- source recorded action;
- target completion timing shifts;
- R1 moves issue time but replays the source action;
- live target controller selects a different action;
- support failure highlighted at action projection.

Goal: a systems reviewer understands the paper before seeing notation.

### Figure 2 — Replay Validity Dimensions + quotient intuition

Prefer one compact two-panel figure:

- left: timing / operation / action / admissibility / induced workload as distinct obligations;
- right: feedback values partitioned into decision classes, showing one cross-class pair (N2-like) and one within-class pair (N2b-like).

This figure should visually explain why `feedback changed` is neither necessary nor sufficient for semantic invalidity.

### Table 1 — Mechanism / native-workload separation

Rows: E3b Mosquitto, E3c Home Assistant, optionally N1 as a short third row.

Columns should include only decision-useful quantities:

- R1 timing adaptation;
- R1 target support violation;
- R2 target support violation;
- native R1 work;
- native R2 work;
- R2/R1 workload ratio.

Do not dump every trial statistic into the paper.

### Table 2 — Natural-controller semantic predictions

Three rows are enough:

| Case | Raw feedback relation | Operation relation | Action relation | AgentMark prediction | Native outcome |
|---|---|---|---|---|---|
| N1 official Motion-Light | crosses decision boundary | differs | differs | recorded action unsupported | confirmed |
| N2 Better Thermostat | crosses decision boundary | same | different | operation-only view misses shift | `TV_op=0`, `TV_action=1` |
| N2b Better Thermostat | feedback differs, same decision class | same | same | replay remains supported | `TV_feedback=1`, quotient/action TV=0 |

This table is the empirical heart of the generalization argument.

## 10. Results reporting discipline

Separate three kinds of evidence.

### Exact structural invariants

Report as exact counts/equalities, not p-values:

- support failure 12/12 or 0/12;
- exact native call/PUBLISH counts;
- exact TV values in deterministic kernels;
- exact action identities;
- exact validator/checksum gates.

### Timing measurements

Use paired per-trial summaries and uncertainty intervals. Timing is evidence that R1 genuinely adapts; it is not the primary semantic endpoint. Avoid significance-test theater.

### Replication/provenance

State enough to establish rigor:

- immutable image/source hashes;
- independent replicas/validators;
- native conservation where applicable;
- preregistered natural-controller selection/predictions.

Move raw checksums and detailed manifests to the artifact, not the nine-page body.

## 11. Related-work order

The closest work must appear first, not be buried.

### 11.1 Feedback-aware / closed-loop replay and emulation

EdgeDroid, CellReplay, NeuralEmu, CommCanary/decision-fidelity work, and any stronger newly found nearest neighbor.

Opening sentence should concede the shared insight: feedback/environment coupling can make naïve replay misleading.

Then distinguish the object: AgentMark asks when the **recorded action itself remains controller-semantically admissible under changed target feedback**, at an explicit projection, and can evaluate rigid/timing-aware/domain-specific replay mechanisms rather than proposing only one closed-loop mechanism.

### 11.2 Conformance / trace inclusion

Acknowledge ioco-style output inclusion, trace inclusion, bisimulation, conformance testing. Distinguish source-recorded vs target-feedback conditioning and workload-level benchmarking consequence.

### 11.3 Off-policy evaluation / support overlap

Acknowledge that support/absolute continuity is classical. Distinguish the systems object: native replay workload validity under a changed reactive environment.

### 11.4 Pervasive-system benchmarking relevance

Tie back to smart environments, middleware, sensor-driven controllers, and reproducible systems evaluation. This is where venue fit becomes explicit rather than assumed.

## 12. PerCom-specific positioning

The paper should look like a **systems methodology paper for reactive pervasive infrastructure**, not a formal-methods paper that happens to use Home Assistant.

Foreground:

- middleware and sensor/actuator feedback;
- smart-environment automation;
- benchmark/workload validity;
- native Home Assistant and MQTT evidence;
- independently authored controller behavior.

Use the formal model to explain and predict systems behavior, not as an end in itself.

## 13. Double-blind and artifact safety

During review:

- no author names/affiliations in the manuscript;
- no GitHub/website/Zenodo link that reveals author identity;
- self-citations in third person, not omitted;
- internal run IDs/hashes may be used in notes but should not create identity-revealing external links in the submitted PDF;
- check supplementary-material rules before attaching anything externally hosted.

After acceptance, the sealed artifacts are a strength. PerCom explicitly notes artifact presence as one criterion for Best Paper consideration. Prepare the artifact cleanly, but do not trade double-blind safety for early public linking.

## 14. Reviewer kill tests the draft must survive

### R1 — “Closed-loop replay already exists.”

Answer in Intro + Related Work: yes; AgentMark's object is replay admissibility/validity, projection-explicit decision equivalence, and workload certificate, mechanism-independent.

### R2 — “This is just trace inclusion/support overlap.”

Answer: those primitives are acknowledged; new systems methodology conditions the source-recorded action on target feedback and connects it to replay workload validity/native benchmark consequence.

### R3 — “You designed ACT2/VERIFY to win.”

Answer with N1/N2/N2b external/official controllers chosen under locked inclusion policy and classified by the same theory.

### R4 — “Operation names are sufficient.”

N2: exact `TV_operation=0`, `TV_action=1` on same `climate.set_preset_mode` operation.

### R5 — “You flag any feedback change.”

N2b: exact raw feedback TV=1 but quotient/action TV=0; native target and replay both issue supported `away` in 12/12 replicated trials.

### R6 — “R2 has 1.5x work because you programmed it that way.”

Answer narrowly: exactly. The methodological consequence is that replay semantics determine which controller-induced workload is benchmarked; native conservation shows the workload difference is real, not observer loss. Do not claim 1.5x is universal.

### R7 — “Your math is classical.”

Agree about contraction/support primitives. Novelty is the replay-validity object/methodology and systems evidence, not the probability inequality.

### R8 — “This says nothing about physical homes/devices.”

Agree and scope: claim is controller/middleware replay validity, not RF/device/ecological validity.

### R9 — “Step checks do not prove whole-trace validity.”

Agree and state prefix-conditioned target-state requirement explicitly. Never silently reuse source controller state after divergent prefixes.

### R10 — “Why PerCom?”

Answer from page 1: reactive pervasive systems are driven by sensor feedback and middleware controllers; replay is used to evaluate their behavior; AgentMark identifies when the replay workload is not the workload the target pervasive controller would generate.

## 15. What to cut first if pages overflow

Cut in this order:

1. experiment chronology and engineering anecdotes;
2. detailed provenance hashes from body;
3. secondary timing/boundary plots;
4. legacy projections not used by headline claims;
5. full proofs of classical inequalities;
6. redundant natural-controller implementation detail.

Do **not** cut:

- explicit declared projection;
- target-conditioned support criterion;
- decision-equivalence quotient;
- N2 and N2b opposite semantic witnesses;
- the timing-aware failure result;
- exact 1.5x native workload consequence;
- nearest prior-art distinctions;
- limitations/forbidden claims.

## 16. Immediate next production sequence

With empirical expansion stopped, the smartest sequence is:

1. **manifest-driven results extraction** from sealed E3b/E3c/N1/N2/N2b into one machine-readable paper-results table;
2. lock exact statistical language for timing vs structural invariants;
3. generate Figure 1, Figure 2, Table 1, Table 2 from that manifest;
4. write Introduction + Formal Model + Results first;
5. run nearest-neighbor prior-art red team and rewrite novelty sentences;
6. complete Experimental Design / Related Work / Limitations;
7. compile to the official IEEE two-column template and enforce a hard 9-page gate;
8. run three adversarial reviewer passes: systems, theory/methodology, PerCom-fit.

No new empirical experiment enters this sequence unless one of those passes identifies a specific fatal evidence gap.