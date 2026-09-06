# ReplayMark BT→MQTT Phase-B carrier-precondition addendum

**Status:** FROZEN BEFORE ANY LIVE QUALIFICATION WITH THIS PRECONDITION  
**Parent protocol:** `851960e59aa3a68fb90ef199f1dbcfefe5fcd3c0`  
**Scope:** Phase-B runtime qualification only. Phase-A selector, controller actions, continuation, preset temperatures, MQTT topic/QoS, and Phase-C queue predictions remain unchanged.

## Why this addendum exists

The first qualification in which the frozen external automation was actually materialized through Home Assistant's native `automation.reload` path was run `34043088139` at execution head `ea580470c24c6f46028ba8a73cdd0951c4067e07`. It established the frozen controller-level realization exactly: TARGET_NATIVE issued four Better Thermostat preset calls and REPLAY issued two. However, both modes produced zero child `set_temperature` calls and zero measured MQTT temperature commands.

Source inspection of the already-pinned Better Thermostat revision `b86561f61e5ba1259fc63e590f4847e9ac743d7f` explains that result without changing any scientific variable. On fresh state, Better Thermostat adopts OFF when all child thermostats are OFF. In its untouched `control_trv` implementation, a target-temperature write is admitted only when the outbound child HVAC mode is not OFF (except the unrelated no-OFF-device path). The qualification's freshly discovered optimistic MQTT Climate child naturally began OFF, so the harness left the carrier administratively disabled while asking Phase B whether preset decisions survive through that carrier.

The parent protocol requires the natural carrier to be exercised and explicitly excludes setup/reset traffic from the measured workload, but it did not specify the initial HVAC enablement state. HVAC mode is not a coordinate of the frozen Phase-A selector state `(presence, motion, night, current_preset)` and is not selected or changed by the frozen external controller.

## Frozen neutral precondition

For every subsequent Phase-B mode, identically and before the measurement observer is admitted:

1. start the same pinned Home Assistant, Better Thermostat, MQTT Climate, and Mosquitto stack;
2. call Home Assistant's public `climate.set_hvac_mode` service on the **actual Better Thermostat entity**, with `hvac_mode=heat`;
3. require Better Thermostat's public HVAC state to become HEAT and allow its untouched control queue to settle;
4. establish the already-frozen quiescent initial preset `sleep` through the actual Better Thermostat entity;
5. allow that setup control cycle to settle;
6. only then clear the in-process observer, publish `READY`, start the independent Mosquitto observer, and admit the frozen four-event measurement cycle.

Any mode/setpoint/MQTT traffic caused by steps 2–5 is setup traffic and remains outside the measured window exactly as required by the parent protocol.

## What may not change

This addendum does **not** permit:

- direct HVAC or temperature calls to the MQTT child during setup or measurement;
- changing room temperature (`19.5 °C` remains the existing harness value);
- changing any Better Thermostat preset temperature;
- changing the source/target state pair or continuation;
- changing the historical or target-native controller action sequences;
- changing measured topic, QoS, observer accounting, or validator expectations;
- changing the MQTT child's advertised capabilities to manufacture a no-OFF device;
- enabling `no_off_system_mode`;
- modifying external-controller, Better Thermostat, Home Assistant MQTT, or Mosquitto source;
- choosing a second carrier state if HEAT activation does not produce the parent's exact Phase-B 1:1/0:0 mapping.

## One-shot decision rule

The HEAT-enabled qualification is a **one-shot carrier-activation repair**, not a search over environments. The independent validator remains unchanged and still requires exactly:

- TARGET_NATIVE preset sequence `home → comfort → home → sleep`, child temperature sequence `20 → 21 → 20 → 18`, and four QoS-1 measured MQTT commands;
- REPLAY preset sequence `away → sleep`, child temperature sequence `16 → 18`, and two QoS-1 measured MQTT commands;
- exact service/message conservation and reset-free final feedback.

If this precondition does not satisfy the unchanged validator, the capstone is killed under this protocol family. No room-temperature adjustment, preset tuning, alternate state pair, alternate continuation, alternate device capability, or message-accounting repair is admissible afterward.

A passing run may be promoted only with this addendum cited alongside the parent protocol; it must not be represented as if the HVAC precondition had been explicitly frozen in the original parent text.
