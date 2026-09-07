# E3b Runtime Cost Characterization — Frozen Measurement Protocol

Status of this increment: **measurement only**.

This increment does not change ReplayMark semantics, the E3b realization
boundary, same-task correlation, the runtime semantic bridge, R1 execution, or
fallback policy. It measures the already-frozen runtime chain after Integrated
Frozen Runtime Conformance has passed.

## Scientific question

What does the frozen ReplayMark runtime path actually cost, where is that cost
spent, and how does it scale with the number of task certificates?

No optimization is admitted in this increment. Performance values are
descriptive evidence, not promotion thresholds.

## Hard separation of measurement strata

### 1. Online capture microcost

The exact production `_ClientProxy` and `_TimeProxy` wrappers are benchmarked
against no-I/O deterministic delegates. This isolates Python-side capture cost
from MQTT broker/network variance.

The publish microbenchmark compares direct delegate calls with the exact capture
proxy in paired same-round measurements. The time-proxy measurement separately
reports ordinary proxy calls and the one-shot armed path. These numbers do not
claim to be broker round-trip latency.

### 2. Live corpus acquisition

A real Eclipse Mosquitto 2.1.2 run materializes 64 frozen R1 shadow tasks. Corpus
acquisition is intentionally **untimed**.

After the corpus is materialized, `Harness.close()` disconnects Paho and stops
its loop thread. Only then does semantic timing begin. Timed semantic stages
therefore make no network call and do not execute concurrently with R1 workload.

The live corpus is the delayed-feedback negative path:
`not_visible_by_deadline -> INVALID -> DO_NOT_REUSE`.

For branch-sensitive cost comparison, a second corpus is derived from each live
record by inserting exactly one definition-valid positive event inside the
frozen inclusive observation boundary. Those 64 records are explicitly labeled
`derived_positive`; they are not presented as additional live empirical
outcomes. The independent integrated literal oracle must classify them as
`confirmed_by_deadline -> VALID -> REUSE`.

## Stage timing

The measurement runner records p50/p95/p99 plus mean, standard deviation, MAD,
minimum, and maximum using `time.perf_counter_ns()`.

Each timing sample is an average over multiple calls. Stage order is shuffled
deterministically every round to reduce monotonic thermal/scheduler drift, and
garbage collection is disabled only inside hot timing loops.

Measured stages:

- observation realization
- historical-action realization
- `correlate_e3b_runtime_pair()` total
- adjudication
- R* from an already-computed adjudication
- `certify_reuse()` total
- contract fingerprint
- claim fingerprint
- chained certificate assembly
- chained certificate serialization
- SHA-256 over pre-serialized certificate bytes
- full certificate fingerprint
- shadow bridge total
- full raw-record-to-certificate offline pipeline

### Important non-existent seam

`correlate_e3b_runtime_pair()` intentionally performs both individual
realizations before evaluating the pairwise relation. There is no production
"correlation-only" API. The report therefore does **not** invent one.

It reports the actual correlate API total and a clearly marked descriptive
residual:

`correlate_total_p50 - observation_realization_p50 - action_realization_p50`.

That residual is not a separately callable production stage and is not used as a
promotion gate.

Likewise, `ExplicitCompiledContract.certify_reuse()` invokes adjudication
internally. R* itself is separately measurable through the already-frozen
`maximal_certified_reuse(adjudication)` function.

## One-time setup

Compilation of the frozen E3b `ExplicitCompiledContract` is measured separately
and labeled pre-runtime setup. It is not mixed into per-task runtime latency.

## Scaling

The full offline path is measured at task counts:

`1, 4, 8, 16, 32, 64`.

Two batch modes are reported:

1. certificate object construction; and
2. certificate construction plus fingerprinting.

For each count the artifact records batch p50/p95/p99, p50 per task, p50
throughput, and an ordinary least-squares fit of median batch latency versus task
count. No linearity threshold is used to force a PASS.

## Measurement validity, not speed, determines PASS

Promotion requires:

- all frozen authorities remain byte-identical;
- all prior semantic/runtime gates re-pass;
- the previous real-Mosquitto R1 non-interference gate re-passes;
- Integrated Frozen Runtime Conformance re-passes;
- 64 live negative and 64 definition-derived positive benchmark cases are
  admitted by the independent oracle and production chain;
- every stage has the complete requested sample count and ordered percentiles;
- semantic certificate identity before and after benchmarking is identical; and
- measurement output is sealed to the exact GitHub HEAD.

There is deliberately **no absolute latency threshold** in this increment.

## Still excluded

- execution policy
- fallback/regeneration
- selective-reuse intervention
- backend optimization
- bitset/Roaring/BDD replacement
- claims that GitHub-hosted runner timings generalize to all hardware

The next optimization decision must be based on the measured bottleneck rather
than on an assumed data structure.
