# N2 Horizon Runtime — measurement correction after run 34010261833

Status: **FROZEN BEFORE CORRECTED RERUN**

The first preregistered runtime execution (GitHub Actions run `34010261833`) produced the predicted semantic sequences on both independent replicas and the producer promoted every frozen semantic gate. The independent validator nevertheless failed every row for one measurement assertion only: it required `climate_preset_before_issue` captured inside an `EVENT_CALL_SERVICE` listener to equal the pre-call preset.

Inspection of the retained raw event evidence shows why that assertion is invalid in Home Assistant 2026.9.0. The service event callback is invoked after the registered service handler has already mutated the Home Assistant state registry, even though the observer's monotonic service-event timestamp precedes the separately delivered climate `EVENT_STATE_CHANGED` callback. Consequently, reading `hass.states` from the service-event listener returns the **new** preset (`away`, `home`, or `comfort`), not a caller-visible pre-handler preset. This is a measurement-location issue, not a failure of either frozen horizon prediction.

The correction does **not** alter:

- the pinned external blueprint;
- the Home Assistant image;
- the Better Thermostat ownership component;
- the two history pairs;
- the frozen continuation suffixes;
- trial counts, runner count, condition order, or promotion predictions;
- the requirement for exact state-transition-before-consequential-service ordering;
- any semantic outcome gate.

The corrected validator no longer treats a state-registry read inside `EVENT_CALL_SERVICE` as a pre-handler snapshot. Instead it independently checks the native climate `EVENT_STATE_CHANGED` evidence, whose `old_state.attributes.preset_mode` and `new_state.attributes.preset_mode` directly establish the exact preset transition:

- depth 1, motion off: `sleep -> away -> home`;
- depth 1, motion on: `sleep -> away -> comfort`;
- depth 2, step 1: no climate transition and no consequential service;
- depth 2, step 2 motion off: `sleep -> home`;
- depth 2, step 2 motion on: `sleep -> comfort`.

The producer field is renamed from the misleading `climate_preset_before_issue` to `climate_preset_seen_at_service_event_callback`; it is retained as diagnostic evidence but is not used to prove pre-handler state.

This correction follows the same fail-closed principle as the earlier N2b v1→v2 observer correction: preserve the scientific pair and predictions, reject an invalid microstep observation claim, and validate only what the runtime actually exposes.
