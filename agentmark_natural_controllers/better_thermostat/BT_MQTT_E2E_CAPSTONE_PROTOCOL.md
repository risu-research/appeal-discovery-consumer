# ReplayMark Better-Thermostat → MQTT → Mosquitto end-to-end capstone

**Status:** FROZEN BEFORE AUTHORITATIVE SELECTOR EXECUTION AND BEFORE LIVE CAPSTONE EXECUTION  
**Branch base:** `9220089e4d4c99b0e85844838f33796ac538da1b` (`replaymark-n2-horizon-runtime`)  
**Purpose:** high-upside capstone only; it does not alter prior N2/N2b, horizon-runtime, D1/D2, or external-transfer authorities.

## 1. Scientific question

Can a replay-invalid historical controller path from an independently authored Home Assistant automation propagate, without a custom action-to-MQTT translator, through a real Better Thermostat entity and Home Assistant's MQTT climate machinery into a real Mosquitto persistent queue, so that the replay and target-native executions imply different lossless-capacity conclusions on one natural pervasive stack?

The intended chain is strictly:

`external automation → Better Thermostat climate entity → Better Thermostat MQTT adapter → Home Assistant MQTT Climate child → MQTT command topic → Mosquitto 2.1.2 persistent offline QoS-1 queue`.

A result is promotable only if every arrow above is exercised by the corresponding upstream/runtime implementation. A hand-written bridge that converts ReplayMark actions into MQTT messages is forbidden.

## 2. Frozen authorities

### External controller

- Repository: `n3roGit/MyHomeAssistantMods`
- Commit: `57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f`
- Path: `automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml`
- SHA-256: `16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443`
- Frozen scoped logic: `night → sleep`; else `!presence → away`; else `motion → comfort`; else `home`; issue `climate.set_preset_mode` only when the selected Better Thermostat entity's current preset differs from the target preset. Boost/eco/activity/writeback are absent or disabled in the frozen scope.

### Better Thermostat

- Repository: `KartoffelToby/better_thermostat`
- Commit: `b86561f61e5ba1259fc63e590f4847e9ac743d7f`
- Qualified version: `1.9.2`
- Qualified component tree SHA-256: `bc648881395399a4d1957380409e1b8ad3c0c056ba9ae30a53b39d5439fef2c0`
- The capstone must load the actual custom integration, not a state-only shell.
- The child TRV must be an actual Home Assistant MQTT Climate entity and Better Thermostat must select its upstream `mqtt` adapter through the pinned implementation.
- Default preset temperatures at the pinned Better Thermostat revision are accepted unchanged unless runtime setup requires only entity-range-compatible values; no preset values may be tuned after traffic is observed.

### Home Assistant

- Core release: `2026.9.0`
- Git tag commit: `dfb5a9e690daaf204b542896e4b595e61a11a401`
- Runtime image authority inherited from N2 horizon realization: `ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293`.
- MQTT Climate must use Home Assistant's own command publication path. Measured command QoS is fixed to 1 so that the broker's persistent offline queue is the actual downstream resource under test.

### Mosquitto

- Version/tag inherited from promoted D1/D2: `eclipse-mosquitto:2.1.2-alpine` / runtime `$SYS` version `2.1.2`.
- Capacity experiment, if reached, uses the documented-default outgoing queue count policy from D2: `max_queued_messages = 1000`, with `max_queued_messages`, `max_queued_bytes`, `max_inflight_messages`, and `queue_qos0_messages` left unoverridden.
- No synthetic dropper is admitted.

## 3. Phase A — deterministic controller witness selection

The authoritative selector must run before any live capstone outcome is observed. It must enumerate the exact frozen 32-state controller scope:

`(presence, motion, night, current_preset)` with three Boolean feedback variables and `current_preset ∈ {away, home, comfort, sleep}`.

A state is **quiescent** iff `current_preset` already equals the frozen controller's target preset under its feedback values.

### 3.1 Eligible source/target pair

The selector may compare only pairs satisfying all of:

1. both initial states are quiescent;
2. both have the same `current_preset`;
3. they differ in exactly one of `presence`, `motion`, `night`;
4. source state is lexicographically smaller than target state under Boolean order `false < true` and preset order `away < home < comfort < sleep`.

This deliberately excludes a count difference created merely by seeding different starting presets or by starting one world already inconsistent with its own controller.

### 3.2 Continuation alphabet

Only real state-change triggers from the pinned automation are admitted:

`presence_toggle`, `motion_toggle`, `night_toggle`.

The periodic time trigger is excluded from primary witness selection because it changes no controller feedback state and is unnecessary for a natural reset-free workload cycle.

Each controller action atomically updates `current_preset` to the selected preset before the next continuation event. `NO_ACTION` leaves it unchanged.

### 3.3 Primary selector objective: shortest reset-free count-separating cycle

Enumerate event sequences of length 1 through 8. A sequence is eligible iff:

- applying the same event sequence to source and target returns **each world to its own exact initial four-tuple**, so the sequence can be repeated without harness resets; and
- the number of non-`NO_ACTION` controller decisions differs between source and target.

Choose deterministically by:

1. shortest cycle length;
2. largest absolute action-count difference at that shortest length;
3. lexicographically smallest `(source_state, target_state, event_sequence)` under event order `presence_toggle < motion_toggle < night_toggle`.

The authoritative selector must emit the selected states, event sequence, complete action sequences, action counts, final states, and a proof that no shorter eligible cycle exists. No live MQTT measurement may influence this choice.

### 3.4 Secondary prefix witness

For diagnosis only, the selector also emits the shortest non-cyclic continuation satisfying the same pair constraints and producing unequal action counts, with the same deterministic tie-breaks. The capacity experiment is governed by the reset-free cycle, not this secondary prefix.

## 4. Phase B — natural-stack qualification, before capacity confirmation

A qualification run may test wiring but may not test a queue boundary. It must establish all of the following on fresh runtime state:

1. the external automation resolves and calls the actual Better Thermostat climate entity;
2. the Better Thermostat config entry is active, not disabled, and its child is the actual MQTT Climate entity;
3. Better Thermostat loads the pinned `mqtt` adapter for that child;
4. a controller preset decision propagates through Better Thermostat control to the child climate service and then through Home Assistant MQTT publication to Mosquitto;
5. on the **single measured command topic**, each admitted controller `SET_*` decision in the selected cycle produces exactly one QoS-1 command publication after stabilization, and `NO_ACTION` produces zero;
6. setup/reset traffic is outside the measured namespace/window; the selected reset-free cycle itself requires no harness state reset between repetitions;
7. no custom action-to-MQTT converter, message duplicator, synthetic loss mechanism, patched third-party source, or manual downstream publication exists in the producer path.

**Fail-closed rule:** if item 5 is not exact 1:1/0:0, this capstone is not promoted by adapting the message accounting after observation. A new protocol would be required.

## 5. Phase C — queue-capacity predictions

Only if Phase B passes may the queue-capacity confirmation run.

Let the frozen selector's reset-free cycle contain `m_R` historical-replay controller actions and `m_N` target-native controller actions. Under the Phase-B-required 1:1 mapping, one cycle produces exactly `m_R` versus `m_N` measured QoS-1 command messages.

With documented-default queue count `Q=1000`, the two predicted lossless cycle capacities are mechanically fixed **before** capacity execution as:

- replay: `floor(1000 / m_R)` cycles;
- target-native: `floor(1000 / m_N)` cycles.

The confirmatory batch sizes are exactly the two boundary neighborhoods `{B_N, B_N+1, B_R, B_R+1}`, deduplicated if necessary, where `B_N` and `B_R` are those two predicted capacities. No other batch size may be substituted after capacity outcomes are observed.

For a batch of `n` reset-free cycles, expected generated counts are exactly `n*m_R` and `n*m_N`; expected delivered count is `min(generated,1000)` under the frozen queue policy, with loss equal to `generated-delivered`.

The primary capstone flip is evaluated at the replay-inferred largest safe batch `B_R`: replay must be lossless while target-native must be lossy exactly as mechanically predicted.

## 6. Execution discipline

- `REPLAY`: execute the historical source action sequence selected in Phase A against the target stack; `NO_ACTION` produces no climate service call.
- `TARGET_NATIVE`: drive the same continuation events through the unchanged external automation in the selected target world and let it make its own decisions.
- A semantic-replay/R2 cross-check may be included only if implemented independently of TARGET_NATIVE; it is not needed for promotion if direct target-native execution is decisive.
- Mode order must be counterbalanced across trials.
- At least two independent GitHub-hosted runners and six trials per canonical boundary point if Phase C is reached.
- Producer writes raw events; independent validator imports no producer helpers and recomputes action/message conservation, broker/config authority, queue loss, and boundary classification.
- Raw evidence must preserve Home Assistant service-call evidence, MQTT command payload/topic/QoS, Mosquitto image/version/config hash, persistent-session reconnect evidence, duplicates, generated/delivered/lost counts, and exact source/target state/action traces.

## 7. Promotion gates

### Gate E0 — source/model integrity
Exact controller/component/HA authorities match Section 2 and the deterministic selector satisfies Section 3.

### Gate E1 — natural carrier
Actual Better Thermostat → actual MQTT Climate → Mosquitto chain is proven with no forbidden bridge and exact 1:1 action-to-command conservation.

### Gate E2 — semantic realization
On the selected reset-free cycle, live direct target-native controller decisions match the frozen selector prediction in every canonical trial; replay executes the frozen historical decisions exactly.

### Gate E3 — broker-native workload realization
Measured QoS-1 command counts equal the mechanically predicted replay/native counts in every canonical trial, with zero duplicates.

### Gate E4 — deployment flip
The documented-default Mosquitto queue produces the exact frozen loss table and opposite lossless/lossy classification at `B_R`.

Only E0–E4 PASS permits manuscript promotion as an end-to-end capstone.

## 8. Kill conditions / anti-overclaim

The capstone is killed, not repaired post hoc, if any of the following is needed:

- custom controller-action → MQTT translation;
- modification of the external automation, Better Thermostat, or Home Assistant MQTT Climate implementation;
- synthetic message multiplication or dropping;
- post-outcome choice of a favorable continuation or queue size;
- use of a state pair that violates Section 3 eligibility;
- replacing direct target-native decisions with ReplayMark's own semantic interpreter;
- counting setup/reset traffic as workload traffic.

A failed capstone does not weaken the prior ReplayMark results; it only means this stronger single-stack closure was not established under the frozen protocol.

## 9. Permitted claim if promoted

A successful result supports only the following bounded claim:

> For one pinned third-party Home Assistant controller carried naturally through pinned Better Thermostat and Home Assistant MQTT Climate into Mosquitto 2.1.2, retaining the historical controller path can change the real broker-native command workload enough to reverse a documented-default persistent-queue capacity conclusion.

It does not estimate prevalence across smart homes, controllers, brokers, or MQTT deployments.