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

Let `K(.|x,a)` be the target-condition transition kernel after concrete action `a`. For a projected class `z`, define the target-supported successor envelope

`Post_T^C(x,z) := union_{b in supp(pi_T(.|x)), phi_C(b)=z} supp(K(.|x,b))`.

For an injected source action `a`, the replay successor support is

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

Hence the observed projected replay trace is in target-native trace support.

### Proof sketch

At each step, condition (2) gives a target-supported witness action `b_t` with the same projected class and with a transition to the *same observed successor* `x_{t+1}`. Starting from the common `x_1`, append these witnesses inductively. The observed replay condition path itself is therefore a coherent target-native witness path. QED.

### Pre-execution corollary

If instead the stronger closure condition

`Post_R(x_t,a^S_t) subseteq Post_T^C(x_t,phi_C(a^S_t))`

holds before execution at every admitted step, then **every** replay successor supported by the injected action preserves target-native projected-prefix realizability.

This gives a clean distinction:

- **post-hoc trace certification** needs the observed successor to have a coherent target witness;
- **pre-execution safe reuse** needs all possible injected-action successors to remain within the target-supported successor envelope.

---

## 5. Necessity attack: why some continuation obligation cannot be removed

The two-step counterexample in Section 2 violates continuation closure at `x0`:

- injected `a` reaches `xA`;
- the only target-supported same-projection witness `b` reaches `xB`;
- therefore `xA notin Post_T^C(x0,z)`.

Both local support checks still pass, but whole-trace realizability fails.

Thus any theorem claiming that pointwise projected support alone composes into target-native trace support is false.

The exact *minimal* global condition is language-level witness coherence, but continuation closure is the sharp one-step condition that makes the existing stepwise audit compositional by induction.

---

## 6. Language-level formulation: exact but too tautological to lead the paper

For a target world `w`, let `L_C(w)` be the prefix-closed language of projected target-native traces. Under incomplete evidence `e` with compatible worlds `Omega(e)`, define

`L_C^-(e) := intersection_{w in Omega(e)} L_C(w)`

`L_C^+(e) := union_{w in Omega(e)} L_C(w)`.

Then a projected prefix `p` is:

- CERTIFIED TRACE-VALID iff `p in L^-`;
- CERTIFIED TRACE-INVALID iff `p notin L^+`;
- UNRESOLVED otherwise.

This is exact and is the trace-language analogue of the current `S^- / S^+` support envelope.

However, as a headline theorem it is again mostly an intersection/union fact. Its value is as a semantic target for the continuation-closure algorithm, not as the quantum jump itself.

---

## 7. Prefix-conditioned R*: the naive maximality claim also needs narrowing

Given a certified prefix `p`, define the guaranteed native next-action set

`G_e(p) := { z | pz in L_C^-(e) }`.

A prefix-sound online policy may reuse a recorded next class `z` only when `z in G_e(p)`.

This gives a valid **local maximality** statement:

> Among policies using the same evidence and required to keep the extended prefix certified target-realizable, reuse on `G_e(p)` is maximally permissive at the current step.

### Attack on global maximality

It is **not** globally reuse-maximizing over a horizon without a cost/objective model. A safe source action can be reused now yet steer the system to a branch where many later source actions must be regenerated, while regenerating now could enable more later reuse. Therefore a greedy `R*_seq` cannot be called globally optimal merely from support semantics.

The current paper already avoids global cost-optimality for one-step `R*`; the trace extension must preserve that discipline.

---

## 8. Quantifier attack under uncertain evidence

For trace-level certification the relevant validity statement is

`for every admitted world w, there exists a coherent target-native witness path in w`.

This is `forall w exists path`, not `exists one path forall w`.

Likewise, checking that every action is supported at every time under independently constructed world/state sets can silently swap or fragment witnesses. A sound trace audit must propagate **reachable compatible path sets**, not recompute unrelated stepwise supports from scratch.

This is exactly where model-prefix propagation earns its keep. The trace extension should therefore be presented, if ever used, as a formal closure of the existing evidence hierarchy rather than as evidence that the current hierarchy was wrong.

---

## 9. Projection attack: benchmark equivalence may be too coarse for future composition

A consequential projection `phi_C` can be perfectly adequate for a one-step benchmark claim while merging actions with different future effects. The Section 2 counterexample exploits exactly this.

Therefore a whole-trace claim requires one of three things:

1. a sufficiently fine projection whose classes are continuation-closed;
2. explicit transition evidence showing that the *specific observed successor* has a same-class target-native witness; or
3. a forward-simulation relation that tracks replay and target-native states even when they are not identical.

Option (3) is the most general but moves directly into classical simulation/bisimulation territory. That is mathematically respectable but likely too expensive for the current PerCom paper unless the simpler continuation-closure result proves insufficient.

---

## 10. Novelty red team against formal-methods prior art

Generic trace containment, simulation, bisimulation, and congruence of behavioral equivalences are established formal-methods concepts. Therefore ReplayMark should **not** claim novelty for discovering that whole-trace consistency needs transition coherence.

The replay-specific opportunity is narrower:

> characterize exactly when ReplayMark's claim-relative one-step support certificate composes into a target-native trace certificate, and show that the missing obligation is continuation closure of the injected source action relative to target-supported same-projection witnesses.

That link is specific to the paper's source-action / target-controller / benchmark-projection relation. It can be positioned as a compositionality boundary built on established simulation ideas, not a new theory of transition systems.

---

## 11. Fit with the current paper

### What survives strongly

- The current stepwise validity definition remains correct for the claim it makes.
- The existing support envelope remains correct for pointwise evidence uncertainty.
- The prior warning that supplied-state checks are stepwise is vindicated, not overturned.
- Model-prefix certification becomes the natural place where continuation witnesses can be propagated.

### What must not be claimed

- “Every locally valid replay trace is target-native realizable.” False without continuation closure.
- “Joint support is a new theorem because marginals do not compose.” Too elementary and partly attacks the wrong object.
- “Prefix R* globally maximizes reuse.” False without horizon/cost assumptions.
- “The current experiments already validate arbitrary whole-trace compositionality.” They do not.

---

## 12. Current red-team verdict

### Naive joint-trace proposal

**KILLED as stated.** It is mathematically correct at the marginal-support level but too elementary, and it does not expose the real compositional gap in ReplayMark.

### Salvaged direction

**PROMISING:** `local support + continuation closure -> target-native trace realizability`.

The key new phrase is **witness coherence**: a target-supported action that justifies reuse at one step must also be able to justify the successor condition on which later reuse decisions are based.

This is a materially stronger and more precise result than the original `AB/BA` marginal counterexample. It survives exact-state conditioning and directly explains when the existing stepwise criterion composes.

### Manuscript status

**DO NOT INTEGRATE YET.** Before any manuscript change, this result needs one more proof/definition pass around (i) feedback/environment state sufficiency, (ii) stochastic transition support, and (iii) whether `K` should range over full target condition or a claim-relevant state abstraction. The paper should only adopt it if it can be stated in <~0.25 page without turning ReplayMark into a generic transition-system paper.
