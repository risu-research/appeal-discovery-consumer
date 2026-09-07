# Gate S2-Q — Source-Only Calibration and D* Seal

Status target: **derive exactly one mixed-stress delay from source-only evidence, then seal it before any shifted-target outcome exists.**

Frozen parent:

- S2-P protocol authority: `ce92490e546e25cae980b7c84806ff655f2c947d`
- protocol blob: `0a2160ed7fa7e50ba5641fa251b334e9e0cb7beb`
- S1 certified execution admission remains frozen underneath S2-P.
- S0 semantic/runtime authority and the micro-optimization freeze remain intact.

## Why S2-Q is a separate gate

S2-P fixed the calibration rule before data. S2-Q is not a new hypothesis and does
not alter that protocol. It is a preregistered evidence checkpoint separating the
source-derived stress point from the shifted target experiment.

If calibration and target execution occurred in one result-bearing run, a reviewer
would have to trust that the target outcomes did not influence the selected delay.
S2-Q removes that ambiguity by sealing the source artifact and `D_star` before S2-E
is permitted to exist.

## Frozen source-only workload

The runner executes exactly the S2-P source calibration:

- Eclipse Mosquitto 2.1.2;
- device state delay exactly 0 ms;
- three fresh replicates;
- 192 tasks per replicate;
- 576 total tasks;
- ACT1 only;
- wave size 32;
- wave period 300 ms;
- verify boundary 100 ms;
- task timeout 1000 ms;
- no ACT2 candidate;
- no ReplayMark certificate;
- no independent semantic oracle;
- no shifted-target configuration.

Each task records integer monotonic timestamps for task start, ACT1 publication,
verify deadline, task timeout, and the first matching `on=True` A-side state event.
The protocol-defined completion offset is recomputed from those raw integers:

```text
completion_offset_ms =
    (state_on_recv_mono_ns - task_t0_ns) / 1e6
```

## Independent derivation

The live runner reports a preview, but that preview is not trusted. A separate
verifier recomputes the pooled median, p99, and `D_star` from all 576 raw rows.
Promotion requires exact agreement with the runner preview.

The only legal formula remains the frozen S2-P formula:

```text
D_star_ms =
    floor((100.0 - pooled_median_source_completion_ms) + 0.5)
```

Qualification additionally requires:

- every one of the 576 rows is present;
- no task is excluded;
- every source task completes;
- every matching source state is visible by the 100-ms boundary;
- pooled completion p99 <= 80 ms;
- `1 <= D_star_ms < 100`.

If any condition fails, S2-Q is a scientific qualification failure. It is not
permission to inspect a shifted target or choose another formula, verify boundary,
workload shape, or delay.

## Two-commit authority

S2-Q is intentionally split:

1. **Calibration execution commit** — adds only the source-only runner, verifier,
   charter, and workflow. Its first complete calibration artifact is authoritative.
2. **D* seal commit** — after a successful first complete artifact, records only
   the exact `D_star`, source statistics, run/artifact identity, and raw-result
   digest. It executes no additional calibration and no target workload.

S2-E may branch only from the final D* seal authority.

## Failure preservation

The workflow uploads the completed source artifact before enforcing the scientific
PASS/FAIL verdict. Thus a complete failed calibration remains evidence and cannot
be silently replaced by a favorable rerun. Infrastructure failure before a
complete report may be retried only on the exact same commit and parameters.

## Non-goals

S2-Q makes no claim about:

- the existence of a mixed shifted-target workload;
- ReplayMark selectivity on target tasks;
- fallback or regeneration;
- latency improvement;
- new semantic theorems;
- target-wide generalization.

Those questions remain downstream of the immutable D* seal.
