# AgentMark — Reviewer-Facing Claim–Evidence / Generalization Matrix

Status: **pre-N2b decision gate** on branch `agentmark-n2b-decision-equivalence`.
Base: sealed theory/N1/N2 head `4264c43d013178c8babedf772b1c06c5ddbe73cb`.

This matrix is intentionally frozen **before** the N2b native outcome. Its purpose is to determine whether another experiment is scientifically justified and, if so, exactly which missing claim it must test. It is not an inventory of everything AgentMark has run.

## 1. Paper spine

The paper should make only a small number of claims:

**C1 — Timing fidelity is not controller-semantic fidelity.** A replay may adapt issue timing to target execution/completion feedback while still issuing an action that the target-conditioned live controller would not issue.

**C2 — Operation identity is not necessarily action identity.** The same operation/service name can denote consequentially different actions once target class and adapter-declared semantic arguments are considered.

**C3 — Replay semantics can change the workload being benchmarked.** Re-entering the target-conditioned controller can change path and multiplicity, not merely timing error.

**C4 — Raw feedback difference is not itself replay invalidity.** Distinct feedback values that remain in the same controller decision-equivalence class induce the same projected workload; AgentMark must accept such a case rather than flagging feedback change mechanically.

**C5 — The replay-validity criterion is mechanism-independent and transfers across substrates/controllers.** The same semantic principle predicts outcomes in a broker experiment, native Home Assistant middleware, an official HA controller, and an independently authored HA controller.

Everything else is support, scope, or theory. Do not create additional headline claims unless the nine-page paper cannot work without them.

## 2. Claim–evidence matrix

| Claim | Formal object / prediction | Existing decisive evidence | Existing control / falsification | Reviewer objection primarily killed | Paper placement | State before N2b |
|---|---|---|---|---|---|---|
| **C1 Timing != controller-semantic fidelity** | Local target admissibility: for source-consistent recorded `e`, require `K_s^phi(e|y_T)>0`; timing adaptation does not imply this condition | **E3b** Mosquitto: R1 timing shifts ~+145.85 ms yet support violation=1. **E3c** HA: R1 shifts ~+146.04 ms yet support violation=1. **N1** official Motion-Light: R1 shifts ~+35.2 ms yet issues `light.turn_off` while live controller is waiting | E3b feedback-insensitive negative is SAFE; E3c no-shift + insensitive controls; N1 replicated validators | “R1 is feedback-aware, therefore semantically faithful” | Main text, Fig. 1 + one compact results table | **Closed** |
| **C2 Operation != action identity** | Projection is declared: `operation` vs `action=(operation,target_class,variant)` | **N2 Better Thermostat**: exact `TV_operation=0`, exact `TV_action=1`; source `preset_mode=home`, target `preset_mode=away`, same `climate.set_preset_mode` | N2 no-feedback-shift control gives same HOME action under both native/replay; v4 explicit pre-action snapshots; two replicas | “Service/operation name is sufficient semantic identity” | Main text; likely one two-row semantic projection panel | **Closed** |
| **C3 Replay semantics changes benchmark workload** | Target-conditioned replay may change path / multiplicity when controller decision class changes | **E3b** broker-native PUBLISH exactly 512/512/768 for R0/R1/R2; **E3c** native work exactly 256/256/384; exact R2/R1=1.5 in both | Native conservation; independent validators; E3b rejected 80 ms endogeneity hypothesis remains rejected | “R2 merely changes timing; workload is fundamentally the same” / “measurement dropped events” | Main text; one workload consequence panel | **Closed** |
| **C4 Raw feedback difference != invalidity** | Decision equivalence `y~y' iff K_s^phi(.|y)=K_s^phi(.|y')`; deterministic exact quotient predicts `TV(c#mu_S,c#mu_T)=TV(W_S,W_T)` | Synthetic feedback-insensitive negative + exhaustive theory/property tests | Current negative is not an externally authored natural controller | “AgentMark just flags any feedback mismatch” / “decision quotient is decorative theory” | Main text only if natural negative exists; otherwise theory + synthetic control | **Open: highest-value empirical cell** |
| **C5 Transfer across substrate / authorship** | Same support/projection criterion should classify replay independently of substrate-specific emulator mechanism | E3b Mosquitto; E3c HA middleware; N1 official HA blueprint; N2 independently authored Better Thermostat controller | Stage-A fail-closed natural-controller qualification; external source hashes; source edited=false | “ACT2/VERIFY was designed to force the result” / “single custom harness artifact” | Main text compressed; provenance in artifact | **Closed enough for PerCom** |

## 3. Generalization matrix by semantic relation

The useful generalization axis is the **relationship between feedback decision classes and projected actions**, not the number of systems.

| Feedback/controller relation | Expected projected workload relation | Natural/system evidence | Theory evidence | Need another experiment? |
|---|---|---|---|---|
| Same feedback / same class | Same action | N2 no-shift control; E3c controls | Trivial from kernel | No |
| Different raw feedback, **same decision class** | Same projected action; replay should remain admissible | **Missing natural witness**; synthetic insensitive controls only | Exact quotient + property tests | **Yes: N2b if clean** |
| Different class, same operation, different action variant | `TV_operation=0`, action-level shift can be maximal | **N2** | Projection-dependent kernel / TV | No |
| Different class, different operation / disjoint action support | Recorded action can become unsupported | **E3b/E3c/N1** | Step support criterion | No |
| Different class changes path / multiplicity | Different induced workload cardinality | **E3b/E3c R2** | Kernel push-forward | No |
| Stochastic classes with overlapping support | Partial workload shift rather than binary support separation | No natural controller | Dobrushin contraction + finite property tests | **No for this paper unless a reviewer-critical hole appears** |
| Target prefix changes later controller state | Validity must condition on actual target prefix/state | Bounded trace tests; empirical R2 paths | Trace API is fail-closed | No universal whole-trace claim |

### Decision

The matrix identifies exactly one missing empirical cell with high marginal value:

> **An externally authored natural controller pair with `y1 != y2` but `[y1]_(s,phi) = [y2]_(s,phi)`, so AgentMark predicts and observes `TV_feedback>0` but `TV_action=0` and accepts replay.**

A generic N3 positive failure witness would mostly duplicate already-closed cells and is therefore lower value.

## 4. Candidate N2b selected before outcome

Pinned Better Thermostat Lean blueprint (same external source as N2) exposes priority:

`boost > sleep > away > eco > activity > comfort > home`.

Candidate pair, with optional triggers absent and night mode off:

- `y_A`: `presence=off`, `motion=off`
- `y_B`: `presence=off`, `motion=on`

These feedback vectors are distinct, but `not someone_home` is evaluated before motion and therefore predicts `target_preset=away` in both states.

At the declared action projection:

- raw feedback TV for point masses on `y_A` and `y_B`: **1**;
- decision-quotient feedback TV: predicted **0**;
- operation workload TV: predicted **0**;
- action workload TV: predicted **0**;
- replaying the source `away` action under `y_B`: predicted **target-supported / SAFE at the local action criterion**.

This pair is preferred over a new controller because it isolates decision equivalence while holding controller source, middleware, action adapter, ownership boundary, and operation constant relative to sealed N2.

## 5. Fidelity model: do not oversell a strict ladder

For the paper, use **progressively stronger replay obligations** rather than claiming every item forms a universal total order:

1. **Timing relation** — when an event is issued.
2. **Operation identity** — which API/service operation is invoked.
3. **Action identity** — operation + target class + declared semantic variant.
4. **Controller admissibility** — whether that action is supported under the aligned target controller state/feedback.
5. **Induced workload/path** — the sequence, branching, and multiplicity generated by target-conditioned control.

Important: timing is partly orthogonal to semantic identity; controller admissibility is a predicate on an action at a target-conditioned decision point; path/multiplicity is a trace-level property. A figure may look ladder-like for intuition, but the text should call these **obligations/dimensions** unless an implication is explicitly proved.

Empirical separations:

- timing adaptation does not imply controller admissibility: E3b/E3c/N1 R1;
- operation identity does not imply action identity: N2;
- frozen action sequence does not imply target-induced workload identity: E3b/E3c R1 vs R2;
- **raw feedback inequality should not imply semantic inequality**: N2b is the planned safe-side witness.

## 6. Claims deliberately left out of scope

These are not missing cells to chase before PerCom submission:

- prevalence across a statistically representative population of controllers;
- physical device, Matter, Zigbee, radio, or household ecological validity;
- Better Thermostat PID/TRV internal execution;
- feedback-aware replay priority;
- novelty of support inclusion / trace inclusion / TV contraction;
- universal whole-trace validity from stepwise source-state checks;
- E3b 80 ms endogeneity;
- a natural stochastic-overlap controller merely to make the theory section look broader.

## 7. Stop rule after N2b

If N2b cleanly validates the frozen same-decision prediction under the same external controller and HA substrate, **stop adding empirical systems**. The next work becomes paper engineering: statistical reporting split between exact structural invariants and timing uncertainty, related-work moat, manifest-driven figures, nine-page draft, and three-reviewer red-team.

If N2b falsifies the prediction, preserve the result and determine whether the failure is (a) an incorrect static controller interpretation, (b) a measurement/lifecycle defect, or (c) a genuine model mismatch. Do not select a different pair after seeing the outcome merely to recover a positive result.