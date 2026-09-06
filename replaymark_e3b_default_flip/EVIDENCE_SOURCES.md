# External evidence source for documented-default capacity flip

Retrieved: 2026-09-06

Authoritative source: Eclipse Mosquitto `mosquitto.conf` manual

`https://mosquitto.org/man/mosquitto-conf-5.html`

Relevant documented facts used by the frozen protocol:

- `max_queued_bytes` governs queued outgoing QoS 1/2 bytes and defaults to `0` (no maximum).
- `max_queued_messages` is the maximum number of queued QoS 1/2 messages per client above in-flight messages and defaults to `1000`.
- The experiment intentionally omits both directives from its broker configuration, along with `max_inflight_messages` and `queue_qos0_messages`, so the queue-count policy under test is the product's documented default rather than an experiment-selected queue size.

The scientific claim remains bounded to the documented-default queue policy of the pinned Mosquitto 2.1.2 runtime used in the confirmatory experiment.
