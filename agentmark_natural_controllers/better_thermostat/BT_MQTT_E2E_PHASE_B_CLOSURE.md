# ReplayMark Better-Thermostat → MQTT Phase-B closure

**Status:** CLOSED — FAIL-CLOSED; Phase C NOT ADMITTED  
**Authoritative qualification run:** `34044013578`  
**Scientific execution head:** `f53dedfc86ce6b5bceee7f322e0d319cd732d34f`  
**Parent protocol freeze:** `851960e59aa3a68fb90ef199f1dbcfefe5fcd3c0`  
**Carrier-precondition addendum freeze:** `a3008b0ebd0eb29a8fb913b8a1355c63c4a8d6c9`  
**Unchanged validator Git blob:** `10db9a34b46ca2f45990ec210135be500b765a99`  
**Sealed artifact:** `replaymark-bt-mqtt-e2e-heat-qualification`, artifact ID `9992577672`  
**Artifact ZIP SHA-256:** `e2a82b38b1930b32dd407affde6ee7c6fb8f88f94de6293046b556765c059fd5`

## 1. Final execution status

The one-shot HEAT-enabled Phase-B run completed both real-stack producers successfully. The target-native producer completed successfully; the historical-replay producer also completed successfully. The unchanged independent fail-closed validator then returned `FAIL`. Evidence sealing and artifact upload both completed successfully after the validator failure.

This is therefore a scientific qualification failure, not a harness/runtime failure.

## 2. Raw target-native realization

The frozen four-event continuation was driven through the unchanged external automation into the actual Better Thermostat entity. Runtime evidence reported:

- Better Thermostat preset/controller calls: `4`
- Better Thermostat preset sequence: `home → comfort → home → sleep`
- child `climate.set_temperature` calls: `4`
- child temperature sequence: `[5.5, 6.5, 5.5, 5.0]`
- independently observed MQTT QoS-1 rows: `4`
- MQTT payload sequence: `[5.5, 6.5, 5.5, 5.0]`
- final Better Thermostat preset: `sleep`

Thus target-native action-to-child-to-broker count conservation was `4 → 4 → 4`.

The payloads differ from the naive preset-temperature expectation because the pinned Better Thermostat target-temperature calibration layer transforms the BT target into the TRV-facing setpoint before the MQTT Climate child publishes it.

## 3. Raw historical-replay realization

The frozen historical replay executed the selected source actions against a fresh target stack under the same preregistered carrier precondition. Runtime evidence reported:

- Better Thermostat preset/controller calls: `2`
- replay action sequence: `away → sleep`
- child `climate.set_temperature` calls: `0`
- child temperature sequence: `[]`
- independently observed MQTT QoS-1 rows: `0`
- MQTT payload sequence: `[]`
- final Better Thermostat preset: `sleep`

Thus historical replay realized `2 → 0 → 0`, not the Phase-B-required `2 → 2 → 2`.

This is the decisive failure. The pinned Better Thermostat calibration/range semantics collapse both replay-side downstream setpoint changes at the child carrier, so the two controller-level actions do not survive as two broker-native commands.

## 4. Unchanged validator verdict

The preregistered validator was not modified after the HEAT diagnostic. It returned `BT_MQTT_E2E_QUALIFICATION_VALIDATION: FAIL` with errors including:

- target-native child temperature services `[5.5, 6.5, 5.5, 5.0]` rather than the validator's naive `[20.0, 21.0, 20.0, 18.0]` expectation;
- target-native MQTT payloads `[5.5, 6.5, 5.5, 5.0]` rather than that same naive expectation;
- replay child temperature services `[]` rather than `[16.0, 18.0]`;
- replay MQTT count `0 != 2`;
- replay MQTT payloads `[]` rather than `[16.0, 18.0]`.

The payload-equality checks are stricter than the parent protocol's core count gate, but this does not change the scientific disposition: replay independently fails the parent protocol's exact `1 SET = 1 measured QoS-1 command` requirement because two admitted replay SET decisions produced zero child writes and zero MQTT commands.

## 5. Promotion-gate disposition

- **E0 — source/model integrity:** previously closed PASS.
- **E1 — natural carrier:** FAIL for the selected replay cycle because exact action-to-command conservation does not hold.
- **E2 — selected-cycle controller semantics:** controller-level distinction realized (`2` replay actions versus `4` target-native actions), but this alone is insufficient for promotion.
- **E3 — broker-native workload realization:** FAIL. Measured broker-native command counts are `0` replay versus `4` target-native, not the mechanically required `2` versus `4` under the frozen Phase-B gate.
- **E4 — deployment flip:** NOT RUN / NOT ADMITTED.

Therefore Phase C queue-capacity confirmation at `250, 251, 500, 501` MUST NOT be executed under this protocol family, and no `500 cycles: replay lossless / native 50% loss` claim is supported by this capstone.

## 6. Scientific interpretation

The frozen selector established a genuine controller-level consequential distinction: historical replay performs two preset SET decisions while target-native execution performs four. The real Better Thermostat carrier then demonstrates that controller-action inequality need not be preserved by downstream carrier semantics. A natural calibration/range transformation can be non-injective with respect to the selected actions, collapsing distinct upstream actions before broker publication.

The bounded observation supported by this failed capstone is therefore:

> On this pinned Better Thermostat → Home Assistant MQTT Climate stack, a real `2 vs 4` controller-action divergence did not survive as the preregistered `2 vs 4` broker-command divergence; the replay-side actions collapsed before MQTT publication, yielding measured `0 vs 4` broker commands.

This observation must not be repurposed into the frozen queue-capacity flip without a genuinely new preregistered protocol. In particular, the current protocol family forbids post-outcome repair by changing room temperature, preset temperatures, calibration mode, child capabilities, continuation, selected state pair, message accounting, or queue points.

## 7. Provenance disposition

The sealed workflow artifact contains both raw producer results, both independent MQTT observer logs, Home Assistant/Mosquitto provenance, the unchanged validator, the validation certificate, protocol/addendum copies, and `CHECKSUMS.sha256`. The workflow's sealing step verified every listed file before upload. GitHub recorded the artifact digest as:

`sha256:e2a82b38b1930b32dd407affde6ee7c6fb8f88f94de6293046b556765c059fd5`

This document records the terminal scientific disposition only. It does not modify or reinterpret the frozen parent protocol, selector result, raw evidence, or validator.