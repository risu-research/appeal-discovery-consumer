# Gate S2-P4 — Minimal Transport-Timer Discriminator Protocol

Status: **FROZEN AFTER P3 `MIXED_OR_UNLOCALIZED` AND BEFORE ANY P4 OR TARGET EXECUTION.**

P3 showed that the source tail is not confined to one side of the device boundary. It also exposed a repeated ~40-ms-scale structure in forward/device, return-observation, and PUBACK timing while scheduler start lateness remained sub-millisecond. The correct next move is not a larger tracing campaign.

P4 is deliberately the smallest useful control: remove the device process entirely and use one Paho MQTT client subscribed to its own fresh echo topics on the same real Mosquitto 2.1.2 broker. The client publishes the same small QoS-1 payload and records PUBACK and self-echo receive timing. No socket option, QoS, kernel, broker, or ReplayMark semantic is changed.

The complete frozen schedule is 3 rounds × {16,8,4} × 192 tasks = 1,728 source-only rows with the same 300-ms wave period and a fresh topic namespace per cell. The broker restarts each round. The device service must not start.

The protocol also records the client socket's existing `TCP_NODELAY` value and Linux `TcpExtDelayedACKs` counters descriptively. These are diagnostics only; P4 does not claim a delayed-ACK or Nagle cause.

A 40-ms candidate quantum is mechanism-motivated by the Linux TCP delayed-ACK minimum (`HZ/25` when `HZ >= 100`). The classification is prospectively frozen here:

- **SELF_ECHO_REPRODUCES_40MS_STRUCTURE**: either self-echo receive latency or PUBACK latency has at least 10% of complete rows in [35,45] ms and p95 >=35 ms.
- **SELF_ECHO_CLEAN**: both metrics have p99 <20 ms and fewer than 1% of rows exceed 30 ms.
- otherwise **AMBIGUOUS**.

This classification is diagnostic, not a performance promotion. P4 cannot produce W*, D*, a target outcome, fallback, regeneration, or a new ReplayMark theorem.

If self-echo reproduces the structure, the next capstone protocol will stop treating the old 80-ms p99 slack proxy as a device-feasibility property and will qualify the source at the actual semantic evidence boundary instead. If self-echo is clean, only then is one paired two-client relay discriminator justified.
