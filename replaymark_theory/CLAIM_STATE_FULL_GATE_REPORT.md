# ReplayMark q_{C,H} full-model gate — E3b + pinned Better Thermostat

Status: **RESEARCH GATE PASSED FOR (a)–(c); NOT MANUSCRIPT-INTEGRATED; NOT NEW RUNTIME EVIDENCE**

This gate tests whether the proposed horizon-indexed claim-predictive state `q_{C,H}` has enough nontrivial structure to justify further work. It does not assume predictive-state minimization is novel mathematics.

## Exact scope

### E3b

Source model: `agentmark_e3b_lab/e3_mqtt/app/ladder.py`, blob `fcc1768544714f1b11a497a856f8e18d4d2f07dd`.

Controller states: `after_act1`, `verified`, `done`; feedback alphabet: `confirmed_by_deadline`, `not_visible_by_deadline`; claim projection: operation (`ACT2`, `VERIFY`, `DONE`). All six decision conditions `(controller_state,current_feedback)` are enumerated.

### Better Thermostat

Pinned source: `n3roGit/MyHomeAssistantMods@57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f`, path `automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml`, frozen SHA-256 `16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443`.

The model is the entire state space relevant to the frozen N2/N2b configuration: enable on; writeback disabled; boost/eco/activity optional entities absent; changing feedback is presence/motion/night; trigger alphabet is presence toggle, motion toggle, night toggle, and tick; the controlled service boundary deterministically applies the requested preset. Current preset ranges over the four presets reachable under these frozen inputs: away/home/comfort/sleep. Thus the experiment-relevant model has `2^3*4=32` decision states. A secondary robustness check ranges the current preset over all seven presets named by the external controller (56 states); it reaches the same stable quotient.

Claim output is the consequential preset call (`SET_AWAY`, `SET_HOME`, `SET_COMFORT`, `SET_SLEEP`) or `NO_ACTION` when the blueprint suppresses the call because current preset already equals target. No-action is part of the output for workload/path claims.

## Definition

`q_{C,H}` groups two target decision histories/conditions iff their current claim-projected output and all projected output continuations under every admitted future trigger word of length at most `H` are identical.

For deterministic models this is finite-horizon output-behavior equivalence specialized to ReplayMark's claim projection. `H=0` sees only the current controller decision. Current v31 decision equivalence is state-local; in this setting it is the fixed-state restriction of horizon-zero output equivalence.

## E3b exact result — zero-depth fixed point and safe compression

All tested horizons stabilize immediately:

- raw decision conditions: **6**;
- state-local current-decision classes: **4**;
- `|q_{C,0}|=|q_{C,1}|=|q_{C,2}|=...=3`;
- raw-to-stable compression: **2.0x**.

Stable classes are:

1. `ACT2`: `(after_act1,confirmed)` plus both `verified` feedback conditions;
2. `VERIFY`: `(after_act1,not_visible)`;
3. `DONE`: both `done` feedback conditions.

E3b therefore does not manufacture a horizon effect: current operation is already continuation-stable. It nevertheless shows safe cross-state compression missed by the state-local quotient: `after_act1/confirmed` and `verified/*` are predictively identical for the operation claim because all emit ACT2 and enter `done`.

Pair accounting over the six raw conditions:

- local false / predictive false: 11;
- local false / predictive true: **2**;
- local true / predictive false: 0;
- local true / predictive true: 2.

## Better Thermostat exact result — strict horizon refinement plus safe forgetting

For the 32-state frozen-protocol model, exact refinement is:

- `H=0`: **5 classes**;
- `H=1`: **14 classes**;
- `H=2`: **16 classes**;
- `H>=2`: **16 classes**.

So the source has a real finite consequence depth of at most two future trigger events. Current-action identity is too coarse for a two-step claim, while full raw state is unnecessarily fine.

The stable quotient has the exact closed form

`q_C,∞(presence,motion,night,current_preset) ≅ (presence,motion,night,current_preset == target_preset(feedback))`.

Consequences:

- 32 reachable raw states -> **16** predictive classes (**2.0x compression**);
- 56 states when all seven named current presets are admitted -> **16** classes (**3.5x compression**);
- exact identity of a non-target current preset is forgotten because the current action overwrites it;
- all three feedback bits are retained because later partial triggers can expose them;
- the only current-preset information retained is one bit: already at target?

Stable class sizes in the 32-state model are eight singleton classes (already-at-target states) plus eight size-three classes (the three non-target current presets for each feedback vector).

## Strong attack against current decision equivalence

The state-local current-decision quotient also has 16 classes, but the partitions are radically different.

Across all 496 unordered raw-state pairs:

- local false / predictive false: 444;
- local false / predictive true: **24**;
- local true / predictive false: **28**;
- local true / predictive true: **0**.

Thus the two relations share **no nontrivial merged pair** in the frozen 32-state model.

`q_{C,H}` therefore performs both operations the current quotient cannot:

- **refinement:** all 28 pairs merged by state-local current-decision equivalence become predictively distinguishable by `H<=2`;
- **compression:** 24 pairs that state-local equivalence cannot merge because current preset differs are safely merged by the stable predictive quotient.

Current decision equivalence asks whether two feedback observations produce the same action now at fixed state. Predictive equivalence asks whether any claim-relevant continuation can distinguish the histories. A latent feedback bit can be irrelevant now yet matter later; a prior current-preset identity can differ now yet be overwritten before it matters again.

## Shortest distinguishing continuations

Among all **115** pairs with the same current output at `H=0`:

- 24 remain predictively equivalent;
- **81** are distinguished by a one-trigger suffix;
- **10** require exactly two future trigger events.

Against the narrower state-local current-decision relation:

- 28 nontrivial locally-equivalent pairs exist;
- **all 28** are future-distinguishable;
- 24 split at depth 1;
- 4 split at depth 2.

### Frozen N2b pair — depth 1

With current preset `sleep`:

- A: presence off, motion off, night off -> `SET_AWAY`;
- B: presence off, motion on, night off -> `SET_AWAY`.

The automatically generated shortest distinguishing suffix is `presence_toggle`, yielding `SET_HOME` versus `SET_COMFORT`. The N2b pair therefore has exact consequence depth **1** for the preset-action claim.

### Automatically discovered depth-2 pair

With current preset `sleep`:

- A: presence off, motion off, night on;
- B: presence off, motion on, night on.

Both currently produce `NO_ACTION`. No one-trigger word distinguishes them. The shortest suffix is `presence_toggle, night_toggle`, yielding output prefixes `NO_ACTION, SET_HOME` versus `NO_ACTION, SET_COMFORT`.

This depth-2 witness was discovered by exhaustive minimization rather than selected from the paper examples.

## Independent validation

The producer used recursive bounded-future signatures and BFS shortest-witness search. A separate validator used iterative Moore/partition refinement with no recursive-signature reuse and independently reproduced:

- E3b: `[3,3]`, stable 3 classes;
- Better Thermostat: `[5,14,16,16]`, stable 16 classes;
- exact thermostat closed form `(presence,motion,night,at_target)`.

Producer SHA-256: `54a7bf19b8f475fc979acd9c47625f2d5bb7adaf31659c98e0eb646b58bf3c52`.

Result JSON SHA-256: `61dd4e0ddfc5ac203510459787e980579bcca3214d65635f9b0398c494055745`.

Independent validator SHA-256: `ee9ca97eaaa1a5b7509f499b0db3589266a7aa5a38145d28e406a31350b0a69a`.

## Gate answers

### (a) Nontrivial compression/refinement — PASS

E3b gives safe compression without false horizon refinement. Better Thermostat gives both strict horizon refinement and safe forgetting/compression.

### (b) Shortest distinguishing continuations — PASS

The N2b pair has a constructive shortest depth-1 witness; the full frozen controller exposes depth-2 witnesses as well.

### (c) More explanatory than current decision equivalence — PASS, with scope qualification

For **stepwise** replay validity, current decision equivalence remains the right local concept. `q` should not replace it.

For **path/workload claims extending beyond the current decision**, `q` explains whether feedback distinctions harmless now remain harmless over the benchmark's consequence horizon and which raw state distinctions can be forgotten safely.

The clean relation is: current decision equivalence is the horizon-zero fixed-state slice; `q_{C,H}` is the minimal claim-predictive state over the declared horizon.

## Remaining hard attacks

- **Prior art:** finite-horizon behavioral equivalence, Mealy/Nerode minimization, distinguishing suffixes, causal/predictive states, and property-guided abstraction are established. Do not sell the minimization theorem as new automata theory.
- **Horizon selection:** `H` cannot be tuned after observing a split. The benchmark claim must declare/derive its consequence horizon from the measurement endpoint.
- **Empirical boundary:** existing N2b runtime trials validate the local decision only. The depth-1/depth-2 future separations are exact semantic consequences of the pinned source and frozen service model, not already-executed runtime experiments.
- **Over-observation:** a full predictive state is stronger than needed to certify a particular recorded action. Existing `S^- / S^+` remains necessary.
- **Model boundary:** the 32-state result is complete for frozen N2/N2b configuration, not deployments with optional boost/eco/activity enabled, writeback enabled, arbitrary external preset changes, or PID/TRV internals.

## Quantum-jump verdict after actual computation

The technical gate is materially stronger than the earlier idea-stage gate. `q_{C,H}` is not decorative theory:

- E3b is a **zero-depth continuation-stable negative control**;
- Better Thermostat has a strict **0 -> 1 -> 2** horizon refinement, exact **2x** reachable-state compression, a canonical four-bit predictive representation, and constructive depth-1/depth-2 witnesses;
- current state-local decision equivalence is neither a predictive refinement nor a predictive coarsening of `q` in the thermostat model; the relations cross in both directions.

This passes (a)–(c) and justifies one further quantum-jump gate. It is not yet, by itself, sufficient to claim a Best-Paper-level jump because the minimization machinery is prior art and the future-horizon thermostat split is source-model validated rather than runtime-validated.

The strongest ReplayMark-specific interpretation is:

> Replay fidelity is not only claim-relative; for reactive path/workload claims it is **consequence-horizon relative**. The current decision quotient is the horizon-zero case. The minimal target information needed by a longer-horizon claim is the claim-predictive state, while the support envelope tells whether available evidence is sufficient for the particular recorded action without reconstructing that entire state.
