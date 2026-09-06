# ReplayMark E3b documented-default capacity flip — confirmatory outcome

Status: **CONFIRMED / PROMOTED FOR MANUSCRIPT USE**

## Authority

- Frozen protocol: `replaymark_e3b_default_flip/DEFAULT_FLIP_PROTOCOL.md`.
- Protocol-freeze commit: `b8ae9503cbb32a260c32284f0aba0e679480050d`.
- Authoritative execution: GitHub Actions run `34002935533` (run #2; the execution-marker run).
- Execution head: `23b7c85bca6cb85fde9f4361a0f9664d21c8ae8d`.
- Broker runtime: `$SYS/broker/version = mosquitto version 2.1.2`.
- Broker image: `eclipse-mosquitto@sha256:6f8d8a947c506f8a2290ec65cd4bd2bc7cb4d43fb5f6271f861cb013e2ef9797`.
- Confirmation certificate artifact: `replaymark-e3b-default-flip-certificate`, artifact id `9980049060`.
- Certificate artifact archive SHA-256 reported by GitHub: `9f8f78ddd0d80e3cf27f34a1625ed172553690342a31baee788f2764cd2f1dee`.
- Certificate JSON SHA-256 after download: `7b173e2ac4e3b0e31b8f8eff97ae5a1da257c190df92352c8f0c20d0caac98d2`.
- Preserved certificate copy: `replaymark_e3b_default_flip/evidence/default_flip_certificate.json`.

The workflow file itself triggered an earlier installation run (#1) at head `b7f15c9f...`. That run is not canonical. The authoritative run is run #2, triggered only after the explicit execution-marker commit, and all authority statements below refer to run `34002935533` at head `23b7c85b...`.

## External default-policy fact

The Eclipse Mosquitto configuration manual retrieved 2026-09-06 documents `max_queued_messages` defaulting to `1000` and `max_queued_bytes` defaulting to `0` (unbounded). The experiment therefore did not set queue-count or queue-byte limits at all.

Every one of the eight canonical broker configuration artifacts had identical SHA-256

`886f26936b560ebfbf584744c8c4f5f2dd3eeeba946313ad1d2f7f8848bf0858`

and contained only:

```text
listener 1883 0.0.0.0
allow_anonymous true
persistence false
sys_interval 1
log_type error
log_type warning
log_type notice
```

Thus the canonical configs contained none of the four forbidden queue-policy directives: `max_queued_messages`, `max_queued_bytes`, `max_inflight_messages`, or `queue_qos0_messages`.

## Design actually executed

The batch sizes were not chosen after seeing this experiment's outcomes. They were mechanically derived from the already-frozen E3b message multiplicities and the independently documented default queue count `Q=1000`:

- R1 generates exactly 4 measured QoS-1 messages/task, predicting `floor(1000/4)=250` lossless tasks.
- Direct target-native and R2 each generate exactly 6 measured QoS-1 messages/task, predicting `floor(1000/6)=166` lossless tasks.

The frozen confirmatory batch points were therefore exactly `166, 167, 250, 251`: the one-task safe/unsafe neighborhoods around the two independently predicted boundaries.

Two independent GitHub-hosted replicas (`A`, `B`) each ran six trials at every batch size. Each trial executed R1 timing-reactive replay, a direct target-native controller implementation, and the independent R2 semantic-replay table interpreter in a fixed counterbalanced six-permutation order. This produced:

- 144 measured condition executions;
- 30,024 task executions; and
- 12 confirmatory cells for every `(batch size, mode)` result reported below.

The direct target-native condition did not call the R2 interpreter.

## Exact confirmatory result

Every frozen prediction held in every corresponding confirmatory cell:

| Batch tasks | R1 timing replay | Direct target-native | R2 semantic replay |
|---:|---:|---:|---:|
| 166 | 664 / 664 / **0 lost** | 996 / 996 / **0 lost** | 996 / 996 / **0 lost** |
| 167 | 668 / 668 / **0 lost** | 1002 / 1000 / **2 lost** | 1002 / 1000 / **2 lost** |
| 250 | 1000 / 1000 / **0 lost** | 1500 / 1000 / **500 lost** | 1500 / 1000 / **500 lost** |
| 251 | 1004 / 1000 / **4 lost** | 1506 / 1000 / **506 lost** | 1506 / 1000 / **506 lost** |

Each row/mode entry above held in all `2 replicas x 6 trials = 12` corresponding cells.

The independent validator returned `confirmation_pass = true` with `errors = []`. All semantic, implementation, configuration-attestation, primary, and boundary checks passed.

## Independent post-download integrity recheck

After the workflow completed, all eight canonical raw evidence artifacts and the certificate artifact were downloaded again outside the Actions validator path.

The certificate-listed SHA-256 values for all:

- 8 raw JSON reports; and
- 8 broker configuration files

were recomputed from the downloaded bytes and matched **16/16** exactly. All eight downloaded broker configs were rescanned independently and contained zero forbidden queue-policy directives.

This additional check is not part of the scientific endpoint; it is a provenance/integrity check on the canonical evidence bundle.

## Capacity flip

The documented-default queue policy produces an exact benchmark-decision reversal:

- R1 says the broker remains lossless through **250 tasks**.
- Direct target-native execution is already lossy at **167 tasks**, so its largest lossless batch is **166 tasks**.
- R2 independently recovers the same **166-task** native boundary.

At the largest batch R1 declares safe (`n=250`):

- R1 delivers all `1000/1000` generated QoS-1 messages in all 12 cells;
- direct target-native generates 1500 and delivers only 1000, losing exactly **500/1500 = 1/3** in all 12 cells; and
- R2 exactly matches target-native.

The boundary is exact on both sides:

- R1: `n=250` is lossless, `n=251` loses exactly 4 messages per trial.
- Target-native/R2: `n=166` is lossless, `n=167` loses exactly 2 messages per trial.

Timing-reactive replay therefore overstates the documented-default broker's lossless reactive batch capacity by **84 tasks** (`250` versus `166`) in this frozen benchmark.

## Why this result is stronger than the earlier queue-capacity confirmation

The earlier promoted downstream experiment established that R1 can select an explicitly tested 512-message queue as lossless while direct target-native execution requires 768 and loses one third of its workload at q=512.

This extension removes the most obvious reviewer objection to that construction: the queue threshold is no longer selected from the observed 512/768 workload counts. The resource limit now comes from Mosquitto's independently documented product default (`1000`) and the experiment asks a different engineering question: **how large a reactive batch does the stock queue policy appear able to support losslessly?**

The answer still flips: 250 tasks under timing-reactive replay versus 166 under direct target-native execution, with semantic replay recovering the native boundary.

## Manuscript-ready headline

**With Mosquitto's documented default 1000-message queue policy left unoverridden, timing-reactive replay classified a 250-task batch as lossless, while direct target-native execution became lossy at 167 tasks and supported only 166 lossless tasks; at the replay-selected 250-task batch, the native workload lost exactly one third of its QoS-1 messages. Semantic replay recovered the native capacity boundary.**

## Scope

This remains a tightly bounded existence result for the pinned Mosquitto 2.1.2 reactive benchmark. It does not estimate prevalence across MQTT deployments and does not claim that deployed brokers retain the documented default queue policy.
