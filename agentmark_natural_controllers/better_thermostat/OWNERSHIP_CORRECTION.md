# N2 Better Thermostat — Ownership / Registry Bootstrap Correction

Status: **IMPLEMENTATION CORRECTION ONLY; SCIENTIFIC PROTOCOL UNCHANGED**

## Invalid pre-correction execution

The first N2 workflow attempt that reached the Home Assistant harness was GitHub Actions run `33946918917`.

Both replicas failed before a source controller action or any decisive N2 replay outcome was produced. The relevant failures were:

- `Setup failed for 'better_thermostat': Integration not found.`
- `RuntimeError: Device registry not set up`

The run is permanently classified as:

`INVALID_IMPLEMENTATION_CONFIG_ENTRY_AND_DEVICE_REGISTRY_BOOTSTRAP`

It is not a scientific null, promotion failure, or N2 outcome.

## Root cause

The pre-correction harness created a Home Assistant `ConfigEntry` whose domain string was `better_thermostat`, but the corresponding upstream custom integration was not installed in the fresh Home Assistant config directory. Adding that entry therefore asked Home Assistant to set up a domain it could not resolve. Separately, the harness attempted to load the device registry before calling the registry's official `async_setup` lifecycle hook.

Neither defect concerns the frozen HOME/AWAY controller law, the action-identity adapter, the external blueprint, the source/target states, the replay semantics, or the TV prediction.

## Narrow correction

The correction preserves the preregistered controlled-device boundary while making ownership real and auditable.

1. Fetch the actual upstream Better Thermostat custom integration from `KartoffelToby/better_thermostat` at exact commit `b86561f61e5ba1259fc63e590f4847e9ac743d7f` (release `1.9.2`).
2. Verify its `custom_components/better_thermostat/manifest.json` SHA-256 exactly equals `710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28`.
3. Install that exact component tree into each fresh Home Assistant config and require Home Assistant's loader to resolve domain `better_thermostat` and version `1.9.2`.
4. Register a real Home Assistant `ConfigEntry` for that resolved domain with `ConfigEntryDisabler.USER`. The disabled state is deliberate: the ConfigEntry supplies authentic registry ownership, while Better Thermostat's internal PID/TRV control implementation is outside N2's preregistered controlled-device boundary and is not executed.
5. Initialize Home Assistant's device registry using the official lifecycle (`dr.async_setup`, then `dr.async_load`) and the entity registry using `er.async_load`.
6. Create the controlled virtual thermostat's device and entity records through the public Home Assistant registry APIs, owned by that ConfigEntry and platform `better_thermostat`.
7. Do not monkeypatch `device_entities`. The external blueprint resolves `climate.agentmark_thermostat` through Home Assistant's native `device_entities(device_id)` implementation, which reads the entity registry.
8. Keep the preregistered controlled `climate.set_preset_mode` service boundary. This boundary deterministically applies the requested preset and records the native rendered call; it does not determine the external controller's HOME/AWAY choice.

## Why the upstream integration is intentionally not loaded

N2 is a test of an independently authored automation controller's semantic action choice: the external blueprint maps Home Assistant feedback to a rendered `climate.set_preset_mode` action. The preregistration explicitly permits a controlled service implementation at the device boundary.

Executing Better Thermostat's full internal TRV/PID/calibration stack would add unrelated device adapters, physical-TRV assumptions, startup timing, persistence, and control loops. Those mechanisms do not choose the blueprint's `target_preset` and would introduce new confounds into a test whose frozen causal contrast is HOME versus AWAY controller feedback.

The corrected ownership therefore separates two claims cleanly:

- **claimed and tested:** Home Assistant-native loader/domain provenance, ConfigEntry ownership, device/entity registry linkage, `device_entities` resolution, automation parsing/triggering/branching/template rendering, and rendered service-call semantics;
- **not claimed:** Better Thermostat PID/TRV internals, physical thermostat behavior, radio/device-stack behavior, or prevalence across all controllers.

## Scientific invariants unchanged

The correction does **not** change any of the following:

- external controller repository, commit, path, or byte content;
- Home Assistant Core version or immutable container digest;
- source feedback `HOME`;
- target feedback `AWAY`;
- current preset `sleep`;
- source action variant `{"preset_mode":"home"}`;
- target-live action variant `{"preset_mode":"away"}`;
- operation projection definition;
- action projection definition;
- generic variant canonicalization rule;
- 6 target-native / 6 target-replay / 6 no-feedback-shift controls per runner;
- two independent runners;
- exact prediction `TV_operation = 0`;
- exact prediction `TV_action = 1`;
- negative-control requirements;
- requirement that no failed runner be dropped.

## Artifact separation

Corrected producer and validator schemas are bumped from v1 to v2. Aggregate promotion requires v2 on both independent runners. This prevents any pre-correction artifact from being accidentally mixed into the corrected evidence chain.
