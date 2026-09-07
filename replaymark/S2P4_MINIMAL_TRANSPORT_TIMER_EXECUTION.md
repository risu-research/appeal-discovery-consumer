# Gate S2-P4 — Minimal Transport-Timer Discriminator Execution

This execution is the first complete run of the frozen P4 self-echo protocol. It starts the real Mosquitto 2.1.2 broker but **does not start the device service**. A single Paho MQTT 2.1.0 client subscribes to its own fresh topics and publishes QoS-1 messages under the frozen 3×{16,8,4} schedule.

No ReplayMark semantic/oracle module is imported, no target is executed, no ACT2 candidate exists, and no TCP socket option is modified. Existing `TCP_NODELAY` and Linux `TcpExtDelayedACKs` are observed only descriptively.

Scientific validity requires all 1,728 rows and exact frozen identities. `SELF_ECHO_REPRODUCES_40MS_STRUCTURE`, `SELF_ECHO_CLEAN`, and `AMBIGUOUS` are all scientifically valid outcomes; the classifier was frozen before execution.
