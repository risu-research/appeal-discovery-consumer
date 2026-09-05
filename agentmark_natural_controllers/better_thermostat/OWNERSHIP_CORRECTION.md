# N2 Better Thermostat — Ownership / Registry Bootstrap Corrections

Status: **IMPLEMENTATION CORRECTIONS ONLY; SCIENTIFIC PROTOCOL UNCHANGED**

## Permanently invalid implementation runs

### Run `33946918917`

Both replicas failed before a source controller action or decisive replay outcome. Relevant failures:

- `Setup failed for 'better_thermostat': Integration not found.`
- `RuntimeError: Device registry not set up`

Permanent classification:

`INVALID_IMPLEMENTATION_CONFIG_ENTRY_AND_DEVICE_REGISTRY_BOOTSTRAP`

### Run `33963676524`

This was the first v2 ownership candidate. Both replicas again failed before a complete producer result or validator execution. It established two implementation facts:

1. The exact upstream Better Thermostat source **was successfully fetched and recognized by Home Assistant's loader**. The log reported the custom integration and the exact upstream checkout was `b86561f61e5ba1259fc63e590f4847e9ac743d7f` / `1.9.2`.
2. `ConfigEntries.async_add()` was the wrong lifecycle API for ownership-only registration. Home Assistant defines it as an add-and-setup operation. It therefore attempted Better Thermostat dependencies, including recorder, even though the experiment intended the entry only as disabled registry ownership.
3. Repeated fresh Home Assistant instances plus per-instance custom-component directories exposed a second harness problem: Python/Home Assistant custom-component discovery retained the first temporary namespace path, which was deleted during per-trial cleanup. A later fresh instance therefore encountered a stale custom-component path.

Permanent classification:

`INVALID_IMPLEMENTATION_ADD_AND_SETUP_PLUS_STALE_CUSTOM_COMPONENT_PATH`

No v2 result JSON was produced, independent validation was skipped, and no N2 TV outcome is admitted from this run.

## Corrected ownership architecture

The correction separates **upstream integration authenticity qualification** from **per-trial runtime ownership**.

### A. One-time upstream qualification before any scientific action

- Fetch the actual upstream Better Thermostat component from `KartoffelToby/better_thermostat` at exact commit `b86561f61e5ba1259fc63e590f4847e9ac743d7f` (release `1.9.2`).
- Verify `custom_components/better_thermostat/manifest.json` SHA-256 exactly equals `710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28`.
- Compute a deterministic component-tree SHA-256 over relative paths and file bytes.
- Install those exact bytes in a dedicated qualification Home Assistant config.
- Require Home Assistant's loader to resolve domain `better_thermostat` and version `1.9.2`.
- Do **not** invoke Better Thermostat setup or its PID/TRV logic.
- Keep this qualification config path alive for the entire producer run so any retained custom-component namespace remains valid; delete it only after all source, target, replay, and control trials finish.

### B. Fresh per-trial native ownership without setup side effects

Each source, target, replay, and control trial still receives a fresh Home Assistant instance.

For every fresh instance:

1. Construct a real `ConfigEntry` for domain `better_thermostat` with `ConfigEntryDisabler.USER`.
2. Persist it through Home Assistant's own `homeassistant.helpers.storage.Store` under `core.config_entries`.
3. Load it through `ConfigEntries.async_initialize()`.
4. Require the loaded entry to remain exactly `USER`-disabled and `NOT_LOADED`.
5. Initialize DeviceRegistry through `dr.async_setup` + `dr.async_load`, and EntityRegistry through `er.async_load`.
6. Create the controlled virtual thermostat device and entity using public registry APIs. Both records must link to the persisted ConfigEntry; the entity platform must be `better_thermostat` and the exact entity id must be `climate.agentmark_thermostat`.
7. Do not monkeypatch `device_entities`, template rendering, automation branching, or service data. The external blueprint resolves its climate entity through Home Assistant's native `device_entities(device_id)` implementation, which reads EntityRegistry.
8. Keep the preregistered controlled `climate.set_preset_mode` service implementation as the deterministic device boundary. It applies the already-rendered requested preset but does not choose HOME versus AWAY.

This avoids both private `_entries` injection and `async_add()`'s setup semantics.

## Why Better Thermostat internal control is intentionally outside N2

N2 tests an independently authored automation controller's semantic action choice: the external blueprint maps current Home Assistant feedback to a rendered `climate.set_preset_mode` action.

The preregistration explicitly permits a controlled service implementation at the device boundary. Executing Better Thermostat's full TRV/PID/calibration stack would add unrelated device adapters, persistence, startup timing, calibration, and physical-device assumptions. Those mechanisms do not choose the blueprint's `target_preset` and would introduce confounds into the frozen HOME-versus-AWAY contrast.

The corrected evidence boundary is therefore:

- **claimed and tested:** exact upstream integration source provenance; Home Assistant loader recognition of that domain; persisted native ConfigEntry ownership; native device/entity registry linkage; native `device_entities` resolution; automation parsing, triggering, branching, and template rendering; raw rendered service-call semantics; replay support under operation and action projections;
- **not claimed:** Better Thermostat PID/TRV internals, physical thermostat behavior, radio/device-stack behavior, or prevalence across all Home Assistant controllers.

## Scientific invariants unchanged

None of the ownership corrections change:

- external controller repository, commit, path, or bytes;
- Home Assistant Core version or immutable image digest;
- source feedback `HOME`;
- target feedback `AWAY`;
- current preset `sleep`;
- source variant `{"preset_mode":"home"}`;
- target-live variant `{"preset_mode":"away"}`;
- operation projection definition;
- action projection definition;
- generic rendered-service-data canonicalization;
- six target-native, six replay, and six no-feedback-shift control trials per runner;
- two independent runners;
- exact prediction `TV_operation = 0`;
- exact prediction `TV_action = 1`;
- negative controls;
- prohibition on dropping a failed runner.

## Artifact separation

The persisted-ownership producer and validator use schema **v3**. Aggregate promotion requires producer v3 and validator v3 from both independent runners. No v1/v2 artifact can enter a v3 aggregate.
