# ReplayMark joint-trace red team: kill the naive theorem, salvage the compositional core

Status: **RED-TEAM ONLY — NOT MANUSCRIPT-INTEGRATED**

Purpose: aggressively test the proposed “joint trace support / prefix-conditioned R*” quantum jump against the current ReplayMark semantics. The goal is not to preserve the proposal. Anything that survives should do so under stronger definitions and explicit scope.

## 0. Current contract being protected

The current paper intentionally defines a **stepwise**, claim-relative validity predicate. A concrete source action `a^S_t` is locally valid at target condition `x_t=(s_t,y_t)` when its projected class is in target-controller support:

`phi_C(a^S_t) in S_C(x_t)`.

The paper already distinguishes supplied-state checks, observed-prefix checks, and model-prefix certification, and does not claim that arbitrary independently supplied states form one target trajectory. Any trace-level extension must therefore add real content rather than silently relabel an existing limitation.

---

## 1. First candidate: marginal joint-support theorem

Candidate idea:

Let `mu_C^{1:T}` be the target law over projected action traces and `S_C^{1:T}=supp(mu_C^{1:T})`. Let `S_{C,t}` be the marginal projected support at each coordinate. Then

`S_C^{1:T} subseteq product_t S_{C,t}`,

with strict inclusion possible. Example: target traces are only `AB` and `BA`, so each marginal support is `{A,B}` but `AA` has zero joint support.

### Red-team verdict: mathematically true, but **killed as the quantum jump**

Reason 1 — elementary. This is a generic property of joint versus marginal support.

Reason 2 — it attacks a weaker object than ReplayMark actually uses. ReplayMark does not define step validity from unconditional time-indexed marginals. It conditions on target controller state and feedback. In the `AB/BA` example, if controller state is propagated correctly, after choosing `A` the second-step state can exclude `A`; the current model-prefix discipline can already catch the path inconsistency.

Reason 3 — the proposal risks making a straw-man claim: “coordinatewise marginals are insufficient” is not the paper’s current criterion.

**Do not put this theorem into the paper as-is.**

---

## 2. Stronger attack: exact pointwise validity still need not imply a target-native trace

The more serious question is whether *current-state-conditioned* local validity composes.

It does **not** in general.

### Two-step counterexample: projected witness has different continuation effect

Target conditions: `x0, xA, xB`.

Concrete actions: `a,b,c,d`.

Projection:

- `phi(a)=phi(b)=z`
- `phi(c)=c`
- `phi(d)=d`

Target controller support:

- at `x0`: only `b`
- at `xA`: only `d`
- at `xB`: only `c`

Action effects:

- injected source action `a` at `x0` -> `xA`
- target-supported witness `b` at `x0` -> `xB`
- `d` at `xA` -> `xA`
- `c` at `xB` -> `xB`

Replay executes source sequence `a,d`.

At step 1, local ReplayMark validity passes: target supports `b` and `phi(a)=phi(b)=z`.

After the *injected source action* `a`, replay is at `xA`. At step 2, `d` is exactly target-supported at `xA`, so local validity passes again.

Yet the projected replay trace `(z,d)` has **no target-native witness**. A target-native execution at `x0` must take `b`, which reaches `xB`, where the next target action is `c`. Its projected trace is `(z,c)`.

Therefore:

> Even exact local support checks along the actual replay state path do not imply that the projected replay sequence is one trace the target controller could natively generate.

This counterexample survives the objection to the marginal `AA` example. It uses exact current conditions at both replay steps. The failure comes from **witness incoherence across time**: the target-supported action that witnesses local validity at step 1 does not induce the state transition produced by the injected source action.

---

## 3. What this reveals: projection validity and continuation validity are different obligations

Current pointwise validity asks only:

`exists b in supp(pi_T(.|x)) such that phi_C(b)=phi_C(a^S)`.

For whole-trace realizability, this is not enough. The witness action must also be able to explain the continuation that follows the injected source action.

A naive fix is to require pairwise effect congruence for all actions merged by `phi_C`, but that is stronger than necessary. We can derive a sharper support-level condition.

Let `K(.|x,a)` be a transition-support model over a **future-sufficient target execution condition** `x` after concrete action `a`. For a projected class `z`, define the target-supported successor envelope

`Post_T^C(x,z) := union_{b in supp(pi_T(.|x)), phi_C(b)=z} supp(K(.|x,b))`.

For an injected source action `a`, define

`Post_R(x,a) := supp(K(.|x,a))`

when the same target transition semantics apply to the injected action.

### Definition: continuation closure

A locally valid injected action `a` is **continuation-closed** at `x` when

`Post_R(x,a) subseteq Post_T^C(x, phi_C(a))`.

Interpretation: every successor condition the injected source action can produce is also reachable by *some target-supported concrete action in the same benchmark-relevant class*.

This is strictly weaker than requiring every pair of same-projection actions to have identical transition kernels.

---

## 4. Surviving theorem: local-to-trace compositionality under continuation closure

### Proposition A (support-level compositionality)

Consider a finite/discrete target execution model with initial condition `x_1`, controller support `supp(pi_T(.|x))`, transition-support kernel `supp(K(.|x,a))`, and claim projection `phi_C`.

Suppose replay injects concrete source actions `a^S_1,...,a^S_T` and produces target-condition path `x_1,...,x_{T+1}`. If at every step `t`:

1. `phi_C(a^S_t)` is locally target-supported at `x_t`; and
2. the observed replay successor satisfies

   `x_{t+1} in Post_T^C(x_t, phi_C(a^S_t))`,

then there exists a target-native concrete action sequence `b_1,...,b_T` such that for all `t`:

- `b_t in supp(pi_T(.|x_t))`,
- `phi_C(b_t)=phi_C(a^S_t)`, and
- `x_{t+1} in supp(K(.|x_t,b_t))`.

Hence the observed projected replay trace has a target-native witness along the same target-condition path.

### Proof sketch

At each step, condition (2) gives a target-supported witness action `b_t` with the same projected class and with a transition to the *same observed successor* `x_{t+1}`. Starting from the common `x_1`, append these witnesses inductively. The observed replay condition path itself is therefore a coherent target-native witness path. QED.

### Pre-execution corollary

If instead the stronger closure condition

`Post_R(x_t,a^S_t) subseteq Post_T^C(x_t,phi_C(a^S_t))`

holds before execution at every admitted step, then **every** replay successor supported by the injected action preserves target-native projected-prefix realizability.

This gives a clean distinction:

- **post-hoc path certification** needs the observed successor to have a coherent target witness;
- **pre-execution safe reuse** needs all possible injected-action successors to remain within the target-supported successor envelope.

---

## 5. Second-pass attack on Proposition A: what `x` and `K` must mean

The theorem above is only sound if `x` is future-sufficient for both controller choice and continuation semantics.

### Attack 5.1 — hidden history

If two executions share the same visible `(s,y)` but differ in hidden history that affects later transitions, a kernel written only as `K(.|s,y,a)` can merge incompatible futures. The theorem can then manufacture a witness by switching hidden histories between steps.

**Repair:** either (i) define `x` as an augmented execution state/history sufficient for future controller and transition support, or (ii) state the theorem directly over admitted histories rather than assume a Markov state.

### Attack 5.2 — timing is part of the transition semantics

ReplayMark is specifically about reactive timing. A transition model that omits issue time, elapsed time, pending timers, or target feedback evolution can again merge incompatible continuations.

**Repair:** timing/history variables must be included in `x` or in the transition relation whenever they affect future support. The trace theorem must not silently assume that action labels alone determine successor support.

### Attack 5.3 — exogenous randomness / feedback coupling

Marginal transition-support overlap can be misleading if the same successor is reachable under replay and target witness only under mutually incompatible exogenous realizations. If that exogenous variable has future effects, it belongs in the future-sufficient execution condition. Otherwise the witness can swap worlds mid-trace.

**Repair:** the propagated condition must retain every exogenous fact needed to keep future worlds coherent. Equivalently, use a transition relation over complete admitted histories.

### Attack 5.4 — continuous spaces

In continuous state spaces an exact successor typically has probability zero. The finite/discrete “positive probability” shorthand cannot be carried over literally.

**Repair:** keep this theorem explicitly finite/discrete for the present paper, or use topological support / admitted-transition relations. The current empirical protocols are finite/discrete, so there is no need to buy measure-theoretic complexity for a PerCom submission.

---

## 6. Stronger salvage: path-conditioned coherent-witness validity

The phrase “joint trace support” is itself too broad for ReplayMark. The benchmark is not asking whether the source projected trace occurs somewhere in the target distribution. It asks whether it is compatible with the **target conditions actually being evaluated**.

That suggests a sharper trace-level object.

Let the observed/declared target execution-condition path be `x_1,...,x_{T+1}`. For source action `a^S_t`, define the coherent witness set

`W_t^C := { b : b in supp(pi_T(.|x_t)), phi_C(b)=phi_C(a^S_t), and x_{t+1} in supp(K(.|x_t,b)) }`.

### Definition: path-conditioned trace validity

The replayed projected trace is **path-conditionally target-realizable** when

`W_t^C != empty` for every `t`.

### Proposition B (coherent-witness criterion)

For a future-sufficient finite/discrete target condition path, `W_t^C != empty` for every step iff there exists a target-native concrete witness sequence `b_1,...,b_T` that:

1. is target-supported at every observed condition `x_t`;
2. matches every replayed action under `phi_C`; and
3. traverses the same observed condition path `x_1 -> ... -> x_{T+1}`.

The proof is immediate but the criterion is operationally useful: local support supplies an action witness; trace validity additionally requires that the witness explain the next condition. Because every witness is forced to land at the same `x_{t+1}`, the witnesses concatenate rather than fragment.

### Why this is better than generic joint support

- It preserves ReplayMark's target-condition-relative semantics.
- It identifies the exact missing obligation: **support witnesses must compose through the observed successor conditions**.
- It cleanly separates stepwise supplied-state auditing from model/observed-prefix trace certification.
- It avoids claiming that an action sequence is valid merely because it occurs under some unrelated target trajectory.

This is the strongest surviving conceptual core so far.

---

## 7. Necessity attack: why some continuation obligation cannot be removed

The two-step counterexample in Section 2 violates coherent-witness validity at `x0`:

- injected `a` reaches `xA`;
- the only target-supported same-projection witness `b` reaches `xB`;
- hence no `b` belongs to `W_1^C` for observed successor `xA`.

Both local support checks still pass, but path-conditioned trace validity fails.

Thus any theorem claiming that pointwise projected support alone composes into a target-native trace certificate is false.

---

## 8. Language-level formulation: exact but too tautological to lead the paper

For a target world `w`, let `L_C(w)` be the prefix-closed language of projected target-native traces. Under incomplete evidence `e` with compatible worlds `Omega(e)`, define

`L_C^-(e) := intersection_{w in Omega(e)} L_C(w)`

`L_C^+(e) := union_{w in Omega(e)} L_C(w)`.

Then a projected prefix `p` is:

- CERTIFIED TRACE-VALID iff `p in L^-`;
- CERTIFIED TRACE-INVALID iff `p notin L^+`;
- UNRESOLVED otherwise.

This is exact and is the trace-language analogue of the current `S^- / S^+` support envelope.

However, as a headline theorem it is again mostly an intersection/union fact. Its value is as a semantic target for a coherent-witness/path-propagation algorithm, not as the quantum jump itself.

---

## 9. Prefix-conditioned R*: the naive maximality claim also needs narrowing

Given a certified prefix `p`, define the guaranteed native next-action set

`G_e(p) := { z | pz in L_C^-(e) }`.

A prefix-sound online policy may reuse a recorded next class `z` only when `z in G_e(p)`.

This gives a valid **local maximality** statement:

> Among policies using the same evidence and required to keep the extended prefix certified target-realizable, reuse on `G_e(p)` is maximally permissive at the current step.

### Attack on global maximality

It is **not** globally reuse-maximizing over a horizon without a cost/objective model. A safe source action can be reused now yet steer the system to a branch where many later source actions must be regenerated, while regenerating now could enable more later reuse. Therefore a greedy `R*_seq` cannot be called globally optimal merely from support semantics.

The current paper already avoids global cost-optimality for one-step `R*`; the trace extension must preserve that discipline.

### Attack on evidence stationarity

Executing a reused action can itself change which worlds remain compatible with later observations. `Omega(e)` is therefore not a static set over the whole trace. Any online trace rule must update compatible histories after each action/observation pair rather than reuse a time-zero envelope.

---

## 10. Quantifier attack under uncertain evidence

For trace-level certification the relevant validity statement is

`for every admitted world w, there exists a coherent target-native witness path in w`.

This is `forall w exists path`, not `exists one path forall w`.

Likewise, checking that every action is supported at every time under independently constructed world/state sets can silently swap or fragment witnesses. A sound trace audit must propagate **reachable compatible path sets**, not recompute unrelated stepwise supports from scratch.

This is exactly where model-prefix propagation earns its keep. The trace extension should therefore be presented, if ever used, as a formal closure of the existing evidence hierarchy rather than as evidence that the current hierarchy was wrong.

---

## 11. Projection attack: benchmark equivalence may be too coarse for future composition

A consequential projection `phi_C` can be perfectly adequate for a one-step benchmark claim while merging actions with different future effects. The Section 2 counterexample exploits exactly this.

Therefore a whole-trace claim requires one of three things:

1. a sufficiently fine projection whose classes are continuation-closed;
2. explicit transition evidence showing that the *specific observed successor* has a same-class target-native witness; or
3. a forward-simulation relation that tracks replay and target-native states even when they are not identical.

Option (3) is the most general but moves directly into classical simulation/bisimulation territory. That is mathematically respectable but likely too expensive for the current PerCom paper unless the simpler coherent-witness result proves insufficient.

### Optional deeper refinement: continuation-aware projection

For a condition `x` and concrete action `a`, define its future support signature as the set of target-projected suffixes reachable after executing `a`. A refinement of `phi_C` that also distinguishes unequal future support signatures is continuation-stable. One-sided inclusion of future signatures is enough for replay-to-target trace containment; equality gives an equivalence.

This is essentially a replay-specific face of classical simulation/right-congruence ideas. It is elegant but probably too formal for the current nine-page paper unless it can replace, rather than add to, existing theory.

---

## 12. Novelty red team against formal-methods prior art

Generic trace containment, simulation, bisimulation, and congruence of behavioral equivalences are established formal-methods concepts. Therefore ReplayMark should **not** claim novelty for discovering that whole-trace consistency needs transition coherence.

The replay-specific opportunity is narrower:

> characterize exactly when ReplayMark's claim-relative one-step support certificate composes into a target-condition-aligned trace certificate, and show that the missing obligation is coherent continuation of the target-supported same-projection witnesses.

That link is specific to the paper's source-action / target-controller / benchmark-projection relation. It can be positioned as a compositionality boundary built on established simulation ideas, not a new theory of transition systems.

---

## 13. Fit with the current paper

### What survives strongly

- The current stepwise validity definition remains correct for the claim it makes.
- The existing support envelope remains correct for pointwise evidence uncertainty.
- The prior warning that supplied-state checks are stepwise is vindicated, not overturned.
- Model-prefix certification becomes the natural place where coherent transition witnesses can be propagated.

### What must not be claimed

- “Every locally valid replay trace is target-native realizable.” False without witness coherence.
- “Joint support is a new theorem because marginals do not compose.” Too elementary and partly attacks the wrong object.
- “Prefix R* globally maximizes reuse.” False without horizon/cost assumptions.
- “The current experiments already validate arbitrary whole-trace compositionality.” They do not.
- “A `(s,y)` pair is automatically sufficient state for the trace theorem.” Not unless all history/timing/exogenous facts relevant to future support are encoded or modeled.

---

## 14. Current red-team verdict

### Naive joint-trace proposal

**KILLED as stated.** It is mathematically correct at the marginal-support level but too elementary, and it does not expose the real compositional gap in ReplayMark.

### First salvage: continuation closure

**SURVIVES, but only with an explicit future-sufficient execution state/history.** It provides a usable pre-execution sufficient condition for preserving target-native projected-prefix realizability.

### Strongest salvage: coherent-witness/path-conditioned trace validity

**PROMISING AND SHARPER.** The key concept is **witness coherence**: a target-supported action that justifies reuse at one step must also be able to justify the successor condition on which later reuse decisions are based.

This survives exact current-state conditioning, avoids the straw-man marginal argument, and directly explains when the existing stepwise criterion composes along the target conditions actually being benchmarked.

### Is this a Best-Paper quantum jump yet?

**Not yet proven.** The conceptual result is materially stronger than the naive proposal, but its mathematical core sits close to established simulation/trace-conformance ideas. Its value would have to come from a very compact replay-specific theorem that makes the current paper feel more inevitable, not more encyclopedic.

### Manuscript status

**DO NOT INTEGRATE YET.** Before any manuscript change, the surviving result needs one final proof/novelty pass and a page-cost test. It should enter only if it can replace existing caveat/prose and fit in roughly 0.20–0.30 page without requiring a new experiment or a generic transition-system section.
