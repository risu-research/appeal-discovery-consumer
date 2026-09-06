# ReplayMark E3b documented-default capacity flip — confirmatory protocol freeze

Status: **FROZEN BEFORE IMPLEMENTATION / EXECUTION**

This protocol is a separate confirmatory extension of the already-promoted E3b downstream queue experiment. It does not modify or reinterpret the prior authoritative result on branch `replaymark-e3b-downstream`.

## 1. Scientific question

Can timing-reactive replay overstate the safe workload capacity of Mosquitto when the broker uses its **documented default outgoing QoS queue limit**, rather than a queue capacity selected from the replay result?

The engineering question is fixed as:

> **Under Mosquitto's documented default queue policy, what is the largest 128-style reactive batch size that can execute while an offline persistent QoS-1 consumer later recovers every generated message?**

The point of this extension is ecological: no `max_queued_messages` value is tuned to an observed ReplayMark result. The broker is run without an explicit queue-count override.

## 2. External product fact fixed before execution

The Eclipse Mosquitto configuration manual retrieved 2026-09-06 states that:

- `max_queued_messages` is the maximum number of QoS 1 or 2 messages held in the queue per client above in-flight messages and **defaults to 1000**;
- `max_queued_bytes` **defaults to 0 (no maximum)**; and
- queued QoS-0 messages are disabled by default, while this experiment measures QoS-1 only.

Authoritative public source: `https://mosquitto.org/man/mosquitto-conf-5.html`, section `max_queued_messages` / `max_queued_bytes`.

The confirmatory broker configuration must therefore omit `max_queued_messages`, `max_queued_bytes`, `max_inflight_messages`, and `queue_qos0_messages` entirely. The only non-default settings admitted are those needed to expose the isolated test broker and make the ephemeral run observable (`listener`, anonymous access, disabled disk persistence, `$SYS` interval, and logging).

This is a **documented-default queue-policy** experiment, not a claim that every Mosquitto configuration option is left untouched.

## 3. Frozen platform and semantic mechanism

- Broker tag: `eclipse-mosquitto:2.1.2-alpine`.
- Broker image digest must be recorded in every raw artifact and identical across canonical replicas.
- Broker `$SYS/broker/version` must report `mosquitto version 2.1.2`.
- MQTT QoS: 1 for all measured command/query/state messages.
- Controller decision deadline: 100 ms.
- Target state delay: 150 ms.
- Post-completion gap: 20 ms.
- Wave size: 32 tasks.
- Wave period: 300 ms.
- Per-task timeout: 1200 ms.
- Persistent offline subscriber mechanism and topic accounting are inherited unchanged from the previously qualified and promoted E3b downstream experiment.

The three execution conditions remain:

- `R1_TIMING`: target timing is followed while source semantic sequence `ACT1 -> ACT2` is retained; under the frozen target condition this omits the controller-required VERIFY and must remain support-invalid.
- `TARGET_NATIVE`: direct target-controller implementation; missing feedback at the 100 ms decision deadline causes VERIFY, then ACT2. This code path must not call the R2 interpreter.
- `R2_SEMANTIC`: explicit semantic replay/table interpreter used only as an independent cross-check of native semantics.

## 4. Mechanically derived batch boundaries fixed before execution

The previously frozen E3b semantics establish exact measured QoS-1 multiplicities per task:

- R1: 4 measured messages/task.
- TARGET_NATIVE: 6 measured messages/task.
- R2: 6 measured messages/task.

Given the independently documented default queue count `Q = 1000`, the largest integer batch predicted to be lossless is mechanically determined before execution:

- R1: `floor(1000 / 4) = 250` tasks.
- TARGET_NATIVE/R2: `floor(1000 / 6) = 166` tasks.

The confirmatory experiment therefore tests exactly four predeclared batch sizes:

`166, 167, 250, 251`

They are the safe/unsafe one-task neighborhoods of the two independently predicted capacity boundaries. No batch size may be substituted after confirmatory outcomes are observed.

## 5. Exact frozen predictions

For batch size `n`, expected generated measured QoS-1 messages are `4n` for R1 and `6n` for TARGET_NATIVE/R2. Under the documented default count limit `Q=1000`, the exact downstream predictions are:

| tasks | R1 generated / delivered / loss | TARGET_NATIVE generated / delivered / loss | R2 generated / delivered / loss |
|---:|---:|---:|---:|
| 166 | 664 / 664 / 0 | 996 / 996 / 0 | 996 / 996 / 0 |
| 167 | 668 / 668 / 0 | 1002 / 1000 / 2 | 1002 / 1000 / 2 |
| 250 | 1000 / 1000 / 0 | 1500 / 1000 / 500 | 1500 / 1000 / 500 |
| 251 | 1004 / 1000 / 4 | 1506 / 1000 / 506 | 1506 / 1000 / 506 |

### Primary capacity-flip test

At the largest batch R1 predicts to be safe (`n=250`):

- R1 must classify the documented-default queue policy as **LOSSLESS**;
- direct TARGET_NATIVE must classify the same broker queue policy as **LOSSY**, dropping exactly `500/1500 = 1/3` of its measured target-native workload; and
- R2 must agree with TARGET_NATIVE.

### Exact boundary test

- R1: `n=250` lossless and `n=251` loses exactly 4 messages, establishing a 250-task replay-inferred safe-capacity boundary.
- TARGET_NATIVE/R2: `n=166` lossless and `n=167` loses exactly 2 messages, establishing a 166-task native safe-capacity boundary.

No statistical threshold, latency cutoff, fitted capacity, or post-hoc SLA is admitted.

## 6. Replication and order

- Two independent GitHub-hosted Ubuntu runners: replicas `A` and `B`.
- Six trials per `(replica, batch_size)`.
- Each trial executes all three conditions exactly once.
- Mode order is counterbalanced using the same fixed six-permutation cycle as the promoted downstream confirmation.
- Every `(replica, batch_size)` job starts a fresh Mosquitto process and empty in-memory broker state.
- Every condition uses a unique MQTT namespace and persistent-session client identifier.

Total confirmatory executions:

- `2 replicas x 4 batch sizes x 6 trials x 3 conditions = 144` measured condition executions.
- `30,024` task executions across those condition executions.

Task events are not treated as independent statistical replicates.

## 7. Configuration-attestation gate

Because the scientific claim depends on using Mosquitto's documented default queue policy, every canonical raw artifact must be accompanied by the exact `mosquitto.conf` used in that job.

An independent validator must reject the confirmatory matrix if any canonical config contains any of these directives:

- `max_queued_messages`
- `max_queued_bytes`
- `max_inflight_messages`
- `queue_qos0_messages`

The raw report must record the SHA-256 of the config file, and the validator must recompute and match it from the downloaded artifact.

## 8. Implementation and semantic gates

A condition execution is admissible only if:

1. all workload tasks complete;
2. the online observer independently sees exactly `4n` R1 or `6n` native/R2 measured QoS-1 messages before offline drain;
3. the persistent session is present on reconnect;
4. collector duplicate count is zero;
5. R1 support-violation fraction is exactly `1.0`;
6. TARGET_NATIVE and R2 support-violation fraction is exactly `0.0`;
7. TARGET_NATIVE and R2 each execute VERIFY in exactly `n/n` tasks;
8. broker tag/digest/version and config hash are recorded; and
9. the config-attestation gate passes.

A scientific-prediction failure is preserved as a falsification and cannot be relabeled as an implementation failure unless one of these gates itself fails.

## 9. Independent validation

The experiment runner writes raw JSON only. A separate validator that does not import the runner must consume all eight canonical raw JSON reports plus all eight canonical broker configuration files and verify:

- complete replica/batch/trial/mode coverage;
- common broker image digest and exact runtime version;
- byte-level config hash agreement and absence of all four forbidden queue-policy directives;
- generated-message and semantic conservation;
- exact loss table above;
- TARGET_NATIVE/R2 agreement;
- primary `n=250` classification flip; and
- exact 250-task versus 166-task safe-capacity boundaries.

Only a validator certificate with `confirmation_pass=true` and an empty error list is admissible for manuscript use.

## 10. Reporting scope

If confirmed, the permitted claim is an existence result for this frozen Mosquitto 2.1.2 reactive workload under the product's documented default queue policy: timing-reactive replay can overstate the batch size that appears lossless, while semantic replay recovers the direct target-native capacity boundary.

The result does **not** estimate prevalence across deployed MQTT systems and does not imply that every Mosquitto deployment uses the documented default queue policy.
