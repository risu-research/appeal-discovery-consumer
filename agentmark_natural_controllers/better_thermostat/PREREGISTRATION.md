# AgentMark Natural Controller N2 — Same Operation, Different Action

Status: **FROZEN BEFORE FIRST N2 EXECUTION** on `agentmark-theory-lock`.

N2 tests whether operation-name replay can appear semantically valid while a parameter-sensitive action projection detects that the recorded action is unsupported by the target controller. N2 is intentionally orthogonal to N1: it does not add another timing-replay example and does not require R1.

## 1. Outcome-blind Stage-B selection

N2 is selected from the commit-pinned Stage-A corpus **before any N2 replay outcome is observed**.

Selection rule on the frozen Stage-A seed set:

1. candidate must be `QUALIFIED_STAGE_A` under `context_sensitive_ha_action_sequence_v2`;
2. it must contain a statically named service action with dynamic service data;
3. that action must occur under an explicit reactive `choose` branch;
4. the dynamic service data must be derived from a controller variable whose external source enumerates at least two distinct literal outcomes as a function of Home Assistant state feedback;
5. if more than one candidate satisfies all conditions, select the lexicographically smallest frozen candidate id.

The selected controller is `ha-better-thermostat-lean`.

Stage-A provenance:

- qualification run: `33945243478`
- scanner: `context_sensitive_ha_action_sequence_v2`
- source repository: `n3roGit/MyHomeAssistantMods`
- source commit: `57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f`
- source path: `automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml`
- expected source SHA-256: `16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443`
- Home Assistant runtime: Core `2026.9.0`
- immutable runtime image: `ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293`

The external controller source is executed byte-for-byte. Only declared blueprint inputs and controlled Home Assistant entity states may differ across conditions.

## 2. External controller structure under test

The external blueprint computes `target_preset` in this priority order:

1. `boost`
2. `sleep`
3. `away`
4. `eco`
5. `activity`
6. `comfort`
7. `home`

When the current thermostat `preset_mode` differs from `target_preset`, the controller invokes the same Home Assistant service in every case:

`climate.set_preset_mode`

with dynamic service data:

`preset_mode: "{{ target_preset }}"`.

Therefore distinct controller decisions can share one operation name while differing in consequential service data.

## 3. Frozen action-identity adapter

The adapter rule is substrate-generic and fixed before N2 execution.

For a Home Assistant service call:

- `operation` = `domain.service`;
- `target_class` = canonical domain class of the resolved target entity/entities;
- targeting selectors are not part of the variant: `entity_id`, `device_id`, `area_id`, `floor_id`, and `label_id` are represented through target identity/class instead;
- `variant` = canonical JSON of all remaining rendered service data, recursively key-sorted with scalar values preserved after Home Assistant native template rendering;
- no service-specific parameter names are special-cased;
- an empty remaining data map has variant `{}`.

For N2 this generic rule yields, without special treatment of climate services:

- source variant: `{"preset_mode":"home"}`;
- target-live variant: `{"preset_mode":"away"}`.

The paper-facing `action` projection is `(operation, target_class, variant)`.

## 4. Native registry requirement

N2 must not monkeypatch `device_entities`, template rendering, or controller variables.

Each fresh Home Assistant instance must create native registry state sufficient for the unmodified external blueprint:

- a real Home Assistant `ConfigEntry` for controlled Better-Thermostat test ownership;
- a native device-registry entry attached to that config entry;
- a native entity-registry entry for `climate.agentmark_thermostat` attached to that device;
- the blueprint's own `device_entities(climate_device)` template must resolve the climate entity through those native registries.

The experiment may register a controlled `climate.set_preset_mode` service implementation to observe and deterministically apply the requested preset. That service is the controlled device boundary; controller parsing, variable evaluation, branching, triggering, and template rendering remain Home Assistant native.

## 5. Frozen blueprint inputs

- `climate_device` = native device id created in Section 4
- `presence_group = input_boolean.agentmark_presence`
- `motion_group = binary_sensor.agentmark_motion`
- `night_mode_entity = input_boolean.agentmark_night`
- `enable_switch = input_boolean.agentmark_enable`
- `writeback_enable = false`
- `writeback_bounds_enable = false`
- `boost_entity = ""`
- `eco_entity = ""`
- `activity_entity = ""`

Common state for every decisive condition:

- enable = `on`
- night = `off`
- motion = `off`
- current climate preset before trigger = `sleep`

Thus the first `choose` branch must be eligible because `sleep` differs from either frozen target preset.

## 6. Source condition

Source feedback transition sets presence to `on`.

With all higher-priority conditions false, the external controller computes:

`target_preset = home`

and the native automation must issue exactly one consequential service call:

`climate.set_preset_mode(preset_mode=home)`.

A valid source trace must show exactly one such call, native rendered service data, and a target resolving to the registered climate entity.

## 7. Target condition

Target feedback transition sets presence to `off`.

With all higher-priority conditions false, the external controller computes:

`target_preset = away`

and native target execution must issue exactly one consequential service call:

`climate.set_preset_mode(preset_mode=away)`.

The operation name remains identical to source while action identity changes.

## 8. Recorded replay condition

In a fresh target-state Home Assistant instance, replay the source-recorded action exactly:

`climate.set_preset_mode(preset_mode=home)`

while target controller feedback corresponds to `away`.

Replay does not run the external controller concurrently; target support is evaluated from the frozen external controller kernel and independently checked against a separate native target execution from Section 7.

## 9. Locked semantic prediction

The finite controller kernel for the relevant external control node has two feedback classes:

- `HOME -> climate.set_preset_mode`, target class `climate`, variant `{"preset_mode":"home"}`
- `AWAY -> climate.set_preset_mode`, target class `climate`, variant `{"preset_mode":"away"}`

For the recorded source `home` action under target `AWAY` feedback, N2 predicts **before execution**:

- operation projection: target probability of recorded operation = 1; no support failure;
- action projection: target probability of recorded action = 0; support failure;
- workload total variation at operation projection = exactly `0`;
- workload total variation at action projection = exactly `1`.

This is the decisive N2 falsification target.

## 10. Negative control

Repeat recorded replay under source-equivalent `HOME` feedback.

The same recorded `home` action must then be supported at both operation and action projections, and native source-equivalent execution must emit the `home` variant.

## 11. Replication

- 2 independent GitHub-hosted runners;
- each runner records its own native source trace;
- 6 fresh target-native trials per runner;
- 6 fresh target-replay trials per runner;
- 6 fresh no-feedback-shift control trials per runner;
- no failed runner may be dropped.

Every trial uses a fresh Home Assistant instance so entity state, registry state, automation runs, and service effects cannot leak across trials.

## 12. Promotion gates

N2 is promoted only if both independently validated replicas satisfy every gate.

### External/native integrity

- exact external source SHA-256 matches;
- Home Assistant version and immutable image digest match the frozen values;
- native automation blueprint schema accepts the external source;
- native target/source executions run the unmodified external blueprint;
- native device/entity registries resolve `device_entities(climate_device)` without monkeypatching.

### Source

- exactly one `climate.set_preset_mode` call;
- rendered variant exactly `{"preset_mode":"home"}`;
- current pre-trigger preset is `sleep`;
- target resolves to `climate.agentmark_thermostat`.

### Target native

For all 6 trials per runner:

- exactly one `climate.set_preset_mode` call;
- rendered variant exactly `{"preset_mode":"away"}`;
- no `number.set_value` writeback action;
- no fallback `system_log.write` action.

### Target replay

For all 6 trials per runner:

- replayed event remains the source `home` action;
- operation-projection support failure = false;
- action-projection support failure = true;
- recorded operation target probability = 1;
- recorded action target probability = 0.

### Projection separation

- exact theoretical `TV_operation = 0`;
- exact theoretical `TV_action = 1`;
- native source and target share operation identity but differ in canonical action variant in every decisive comparison.

### No-feedback-shift control

For all 6 trials per runner:

- source-recorded `home` replay is supported under both operation and action projections;
- native source-equivalent control emits the `home` variant.

## 13. Independent validation

A host-side validator separate from the producer must recompute from raw native service events and raw trial metadata:

- source and target variants using the frozen generic canonicalization policy;
- exact service-call conservation;
- source=`home`, native target=`away`;
- operation support and action support independently;
- exact `TV_operation=0` and `TV_action=1` from the locked AgentMark kernel;
- negative-control support;
- source hash, runtime provenance, and replica identity.

Producer summaries are not sufficient evidence.

## 14. Forbidden post-hoc moves

After the first N2 execution begins, do **not**:

- replace `home`/`away` with easier presets because a gate fails;
- special-case `preset_mode` in the action-identity adapter;
- add or remove variant fields after seeing outcomes;
- redefine operation or target class after seeing outcomes;
- monkeypatch `device_entities`, Jinja state helpers, `target_preset`, or blueprint branching;
- edit the external blueprint;
- enable writeback or choose another controller branch to rescue a failed result;
- weaken exact TV or exact support predictions;
- drop a failed independent runner.

Implementation-only corrections are allowed only when they restore the frozen native experiment without changing the scientific conditions above. Every such correction requires a fresh full run.

## 15. Claim boundary

A passing N2 would establish that an independently authored Home Assistant controller can preserve the same operation name while changing consequential action semantics, and that AgentMark's predeclared action projection detects a replay invalidity invisible at operation projection. It would not establish that all service parameters are consequential or that this phenomenon is prevalent across all Home Assistant controllers; broader corpus analysis addresses prevalence separately.
