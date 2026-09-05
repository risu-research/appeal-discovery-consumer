# AgentMark N2b — Preregistration: Natural Decision-Equivalence Negative

Status: **FROZEN BEFORE NATIVE OUTCOME**.

Base branch/head: `agentmark-theory-lock` @ `4264c43d013178c8babedf772b1c06c5ddbe73cb`.
Execution branch: `agentmark-n2b-decision-equivalence`.

N2b exists because the pre-outcome Claim–Evidence Matrix identifies one high-value missing empirical cell: an externally authored natural controller in which **raw feedback changes but the controller decision does not**. N2b is not a search for another positive failure witness.

## 1. Scientific question

Does AgentMark correctly collapse two distinct feedback states that the pinned Better Thermostat Lean controller maps to the same consequential action?

The target prediction is:

`y_A != y_B`, but `[y_A]_(s,action) = [y_B]_(s,action)`.

Therefore, for point-mass feedback laws on the two states:

- raw-feedback TV = 1;
- decision-quotient TV = 0;
- operation workload TV = 0;
- action workload TV = 0;
- a source-recorded `away` action remains target-supported under `y_B`.

A failure of the native controller to satisfy this prediction is scientifically informative and will be preserved; the feedback pair will not be changed after observing the outcome merely to obtain a passing result.

## 2. External controller lock

Use exactly the same independently authored external controller source as sealed N2:

- repository: `n3roGit/MyHomeAssistantMods`
- commit: `57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f`
- path: `automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml`
- SHA-256: `16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443`
- source edited: false

The pinned controller declares the preset priority:

`boost > sleep > away > eco > activity > comfort > home`.

The N2b pair is chosen from that source **before native execution**.

## 3. Middleware / ownership lock

Use the same native Home Assistant and Better Thermostat ownership boundary as sealed N2:

- Home Assistant Core: `2026.9.0`
- immutable image: `ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293`
- Better Thermostat upstream repo: `KartoffelToby/better_thermostat`
- upstream commit: `b86561f61e5ba1259fc63e590f4847e9ac743d7f`
- upstream version: `1.9.2`
- manifest SHA-256: `710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28`
- component-tree SHA-256: `bc648881395399a4d1957380409e1b8ad3c0c056ba9ae30a53b39d5439fef2c0`
- ownership path: persisted USER-disabled `better_thermostat` ConfigEntry -> native DeviceRegistry -> native EntityRegistry -> blueprint `device_entities()` resolution
- Better Thermostat PID/TRV internal control logic is **not** executed or claimed.

## 4. Frozen action projection

Reuse sealed N2's action adapter unchanged:

- operation: `domain.service`
- target class: resolved target entity domain class
- variant: canonical JSON of rendered top-level non-target service data

Expected action in both N2b feedback states:

- operation: `climate.set_preset_mode`
- target class: `climate`
- variant: `{"preset_mode":"away"}`

No semantic field may be added or removed after outcome observation.

## 5. Frozen feedback pair

All unspecified optional triggers are absent, writeback is disabled, and the automation enable switch is on.

### `y_A` — source decision state

- presence: `off`
- motion: `off`
- night mode: `off`
- boost: absent/false
- eco: absent/false
- activity: absent/false

### `y_B` — target decision state

- presence: `off`
- motion: `on`
- night mode: `off`
- boost: absent/false
- eco: absent/false
- activity: absent/false

The two raw feedback vectors differ only in motion.

Static prediction from the pinned controller: because `not someone_home` is tested before motion, both states select `away`.

## 6. Native trigger construction

To avoid changing the trigger dimension across source and target, both native cases are triggered by the same presence transition.

### Native source `y_A`

Pre-trigger state:

- presence=`on`
- motion=`off`

Trigger:

- presence `on -> off`

Final decision feedback:

- presence=`off`, motion=`off`

Expected exactly one consequential controller call:

`climate.set_preset_mode(preset_mode=away)`.

### Native target `y_B`

Pre-trigger state:

- presence=`on`
- motion=`on`

Trigger:

- presence `on -> off`

Final decision feedback:

- presence=`off`, motion=`on`

Expected exactly one consequential controller call:

`climate.set_preset_mode(preset_mode=away)`.

Using the same presence transition prevents the safe-side result from being explained by different trigger types.

## 7. Replay construction

1. Obtain source service data from the native `y_A` source call.
2. Create a fresh target runtime with native automation disabled and target feedback already set to `y_B`.
3. Replay the recorded source call exactly once.
4. Evaluate target support at both `operation` and `action` projections using the frozen AgentMark theory runtime.

Expected replay result under `y_B`:

- exactly one `climate.set_preset_mode(preset_mode=away)` call;
- operation support failure = false;
- action support failure = false;
- action target probability = 1.

A no-shift replay control under `y_A` will also be run and must pass.

## 8. Measurement contract

Each native trial must record two distinct snapshots:

1. **initial snapshot** after HA ownership/automation setup and before the presence transition;
2. **decision-feedback snapshot** immediately after the frozen presence transition and before yielding to wait for the controller action.

The producer must assert that no consequential service call has been observed before the decision-feedback snapshot is captured. If Home Assistant scheduling semantics violate that assumption, the run is an implementation/measurement failure and the observer must be corrected without changing the feedback pair or expected action.

Replay trials must capture the target feedback snapshot immediately before the recorded service call.

`EVENT_CALL_SERVICE` state reads may be retained as diagnostics but are not treated as strict pre-handler snapshots.

## 9. Exact theory predictions

Define a restricted two-symbol deterministic kernel for this frozen pair:

- `AWAY_MOTION_OFF -> climate.set_preset_mode(away)`
- `AWAY_MOTION_ON  -> climate.set_preset_mode(away)`

At the action projection, pre-outcome predictions are:

- `feedback_partition.classes = ((AWAY_MOTION_OFF, AWAY_MOTION_ON),)`;
- raw feedback TV between the two point masses = `1`;
- quotient feedback TV = `0`;
- `TV_operation = 0`;
- `TV_action = 0`;
- pair-restricted policy sensitivity `eta_action = 0`;
- source-recorded away action is source-consistent and target-supported.

The pair-restricted `eta=0` must **not** be described as saying the full Better Thermostat controller is feedback-insensitive.

## 10. Replication and trial lock

- two independent GitHub Actions replicas: replica 0 and replica 1;
- six decisive trials per condition per replica;
- fresh Home Assistant runtime per native/replay trial, matching sealed N2 discipline;
- independent validator must recompute all structural claims from the producer JSON rather than trust producer promotion flags.

Because the core predictions are deterministic structural invariants, 6x2 replication is a robustness/provenance check, not an IID population-size claim.

## 11. Promotion gates

N2b is `PROMOTED_REPLICATED` only if all of the following hold in both replicas:

### Provenance / environment

- external controller hash exact;
- HA version/image exact;
- upstream Better Thermostat manifest/tree exact;
- persisted disabled ownership path exact;
- upstream integration loader qualification occurs before outcome;
- Better Thermostat internal setup remains intentionally uninvoked.

### Source/native semantics

- every source native trial reaches exact final feedback `y_A`;
- every source native trial emits exactly one climate call and no extra consequential action;
- every source native action is exact `away` identity.

### Target/native semantics

- every target native trial reaches exact final feedback `y_B`;
- every target native trial emits exactly one climate call and no extra consequential action;
- every target native action is exact `away` identity.

### Replay semantics

- every target replay occurs under exact target feedback `y_B`;
- every target replay emits exactly the recorded `away` identity;
- operation support failure is false;
- action support failure is false;
- target action probability is exactly 1;
- no-shift replay control under `y_A` also passes.

### Theory/quotient

- raw feedback TV exact 1;
- action decision partition merges the two feedback symbols;
- quotient feedback TV exact 0;
- operation workload TV exact 0;
- action workload TV exact 0;
- pair-restricted action sensitivity eta exact 0.

### Replication

- two independent validators pass;
- both replicas satisfy all producer and validator gates;
- aggregate recomputation agrees exactly across replicas.

## 12. Failure taxonomy / anti-p-hacking rule

If a run does not satisfy the preregistered prediction, classify it before any rerun:

1. **SCIENTIFIC_FALSIFICATION** — the pinned external controller under the frozen final feedback pair produces different projected actions than predicted.
2. **MODEL_MISMATCH** — the external controller's actual executable semantics expose a relevant state/condition omitted from the frozen restricted model.
3. **INVALID_IMPLEMENTATION** — lifecycle/bootstrap/observer/harness behavior prevents the frozen protocol from being executed or measured as specified.
4. **PROVENANCE_FAILURE** — pinned source/image/upstream ownership bytes cannot be reproduced exactly.

Only categories 3 or 4 justify a corrected fresh run, and any correction must preserve the feedback pair, action projection, expected controller action, and promotion thresholds. Category 1 or 2 is retained as the scientific result; do not shop for a replacement feedback pair after outcome.

## 13. Paper-safe interpretation if promoted

The allowed conclusion is narrow:

> In an independently authored Home Assistant controller, two distinct raw feedback states selected before native execution collapsed to the same action-level controller decision. AgentMark's decision quotient predicted zero action-workload shift and accepted replay, matching native execution.

This is evidence that AgentMark is not merely a feedback-change detector and that the decision-equivalence abstraction has a natural-controller safe-side witness.

Do not claim:

- all feedback changes within Better Thermostat are irrelevant;
- the full controller has `eta=0`;
- whole-trace equivalence beyond this aligned decision point;
- physical thermostat or PID/TRV validity;
- population prevalence.