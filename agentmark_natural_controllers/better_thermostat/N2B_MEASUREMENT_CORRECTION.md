# AgentMark N2b — Measurement Correction After Invalid v1 Run

Status: **FROZEN BEFORE ANY VALID N2b OUTCOME**.

This document records an implementation/measurement correction permitted by the N2b preregistration. It does **not** change the scientific feedback pair, action projection, expected action, trial count, promotion thresholds, controller source, middleware image, or ownership boundary.

## 1. Invalid run

GitHub Actions run: `33972326066`, workflow `AgentMark N2b Natural Decision Equivalence`, attempt 1.

Replica 0 failed on the first source-native trial before producing a result JSON or reaching independent validation. The exact failure occurred after the frozen presence transition when the v1 producer attempted to capture a caller-side state snapshot immediately after `hass.states.async_set(presence, "off")`.

Observed exception:

- label: `source_native_yA_t0`
- expected snapshot climate preset at that caller-side microstep: `sleep`
- observed climate preset: `away`
- observed feedback in the failed snapshot: presence=`off`, motion=`off`, night=`off`, enable=`on`

Interpretation: Home Assistant 2026.9.0 may synchronously/eagerly execute the automation and service call before `StateMachine.async_set()` returns to the calling coroutine. Therefore the preregistered assumption that caller-side code can always capture a strict `post-transition / pre-action` microstep is false for this runtime.

This is classified as **INVALID_IMPLEMENTATION**, not scientific falsification. The failure is exactly within the preregistered correction rule: if HA scheduling prevents the specified microstep snapshot, correct the observer without changing the frozen scientific pair or expected action.

The failed v1 workflow, code, logs, and uploaded partial artifact are retained; they are not overwritten or promoted.

## 2. What remains frozen

Unchanged from `N2B_PREREGISTRATION.md`:

- external Better Thermostat Lean source, commit, path, SHA-256;
- Home Assistant Core 2026.9.0 immutable image digest;
- upstream Better Thermostat ownership component commit/version/tree;
- action projection `(operation, target_class, variant)`;
- expected action `climate.set_preset_mode`, target class `climate`, variant `{"preset_mode":"away"}`;
- source feedback `y_A`: presence=off, motion=off;
- target feedback `y_B`: presence=off, motion=on;
- both native cases use the same trigger: presence `on -> off`;
- raw-feedback TV prediction 1;
- quotient-feedback TV prediction 0;
- operation workload TV prediction 0;
- action workload TV prediction 0;
- pair-restricted action sensitivity prediction 0;
- 6 trials per condition per replica, two replicas;
- independent validation and exact promotion gates.

No replacement feedback pair is permitted.

## 3. Corrected measurement contract

The v2 producer replaces the impossible caller-side microstep snapshot with **event-level feedback witnesses** on entities that the climate service handler does not mutate.

Before installing the native automation, a dedicated N2b observer is registered for:

1. `state_changed` on the frozen presence entity; and
2. `call_service` for `climate.set_preset_mode`.

For each native trial, the observer records:

### A. Presence-transition witness

On the exact `presence: on -> off` state-change event:

- monotonic timestamp;
- old and new presence state;
- actual current feedback vector read from HA state: presence, motion, night;
- frozen absence/false status of optional boost/eco/activity inputs.

### B. Service-issue feedback witness

On the controller's `climate.set_preset_mode` call-service event:

- monotonic timestamp;
- service data;
- context id / parent id;
- actual current feedback vector read from HA state.

### C. Post-action feedback witness

After native HA finishes the action, record the feedback vector again.

The promotion gate requires:

- exactly one frozen presence transition;
- exactly one consequential climate service issue;
- transition timestamp <= service-issue timestamp;
- transition feedback vector == the preregistered final feedback vector;
- service-issue feedback vector == the same preregistered final feedback vector;
- post-action feedback vector == the same preregistered final feedback vector;
- source and target native action identities remain exact `away`;
- no extra consequential action.

This establishes the controller feedback at the decision/service-issue boundary without making a false claim about a caller-visible microstep between `async_set()` and eager automation execution.

## 4. Why this is not outcome-dependent weakening

The correction changes only **where feedback is observed**, not what result counts as passing.

In particular, v2 does not:

- remove the requirement that source and target feedback be distinct;
- remove motion from the feedback vector;
- change either final feedback state;
- change `away` to whatever action happens to be observed;
- relax exact action identity to operation-only identity;
- allow multiple actions;
- alter support or TV thresholds;
- alter replication count;
- substitute post-hoc feedback classes.

If native target `y_B` produces any projected action other than the preregistered `away`, N2b fails scientifically.

## 5. Evidence interpretation

The `call_service` listener is **not** used to claim a strict pre-handler climate-state snapshot. N2 already established that such a claim is unsafe. N2b uses it only to read the frozen feedback entities (presence/motion/night), which neither the N2b climate service handler nor the external controller action mutates in this protocol. Equality of the transition, service-issue, and post-action feedback witnesses is required to make that non-mutation explicit.

Thus the v2 correction strengthens the measurement semantics while preserving the preregistered scientific test.