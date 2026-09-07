# Gate S2-P3 — Embedded-Timestamp Tail Localization Result Seal

Status: **FROZEN COMPLETE SCIENTIFIC CHARACTERIZATION.**

The first complete P3 execution is preserved exactly as observed. It was a valid source-only characterization, not a promotion experiment.

## Authority

- protocol: `496ceaead74df882e91b6c86670cc62329e6b88e`
- execution: `8378113f4392a69c282f402fe3ef4fd0c93738f3`
- workflow run: `34159820966`
- workflow job: `101859086158`
- artifact: `10032248216`
- artifact SHA-256: `44e1320f22aac6e152030c582b6fa2dee3411d8d6803e78c1fb363f7d15fcf4f`

## Result

- rows: **1,728**
- clock domain: **VALID**
- scientific verdict: **PASS**
- localization classification: **MIXED_OR_UNLOCALIZED**
- shifted target executed: **NO**
- W*: **not available**
- D*: **not available**

Pooled p99:

- end-to-end completion: **83.470564 ms**
- forward + device: **82.566248 ms**
- post-device observation: **42.082913 ms**
- PUBACK latency: **42.578917 ms**
- scheduler start lateness: **0.753766 ms**

The observed source tail is not localized to only one side of the device boundary. Both pre-device and post-device paths exhibit approximately 40-ms-scale timing structure, while scheduler start lateness remains sub-millisecond at p99. This is descriptive evidence only; it does not establish a TCP, MQTT, kernel, broker, Paho, or device cause.

## Strategic consequence

Do **not** continue load hunting and do **not** launch packet tracing as the default next step. The next allowed step is one prospectively frozen **minimal transport-timer discriminator** that asks whether the same quantized structure appears in a broker self-echo path with the device removed.

If that minimal control reproduces the structure, the capstone should stop treating the old 80-ms source p99 margin as a device-feasibility property and instead move to a prospectively redefined boundary-complete source qualification. If it does not reproduce, the device/two-connection path remains implicated and must be handled explicitly.
