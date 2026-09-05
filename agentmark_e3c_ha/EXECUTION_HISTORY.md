# AgentMark E3c — Execution History

This file is append-only evidence about invalid and valid E3c executions. Scientific failures are not silently reclassified; implementation/measurement failures are retained with their exact run identity and a narrowly scoped correction.

## Attempt 1 — INVALID_IMPLEMENTATION_CLOCK_ORIGIN_AND_EVENT_DRAIN

- GitHub Actions run: `33940019050`
- Frozen execution commit: `e162eff42d37475ab2c11ff8e5faa196841d6b6d`
- Home Assistant Core: `2026.9.0`
- Resolved immutable image: `ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293`
- Replica 0 artifact id: `9961520490`
- Replica 0 artifact SHA-256: `30ff20cf8126606bca13ef314146f144906b4f16ced4d45ce95d306d511a6560`
- Replica 1 artifact id: `9961512973`
- Replica 1 artifact SHA-256: `480ed5f8bba4021b43d6d0edd85df067b59b4e50e4412903916e74a8d03deeac`

### What happened

Replica 1 aborted during source qualification because source task `source_0126` was reported as missing the 100 ms deadline.

Replica 0 completed the scientific workload and produced the expected semantic separation:

- decisive R0 support violation = 100%;
- decisive R1 support violation = 100%;
- decisive R2 support violation = 0%;
- decisive R2 VERIFY fraction = 100%;
- target feedback miss rate = 100% for R0/R1/R2;
- mean R1 ACT2 issue shift vs source = +112.53 ms.

It nevertheless correctly returned `NOT_PROMOTED` because native event conservation and the two negative-control gates failed.

### Why attempt 1 is implementation-invalid rather than scientific evidence

Two predeclared quantities were implemented with the wrong synchronization barriers.

1. **Deadline clock origin.** The preregistration defines the controller deadline as 100 ms after ACT1 *issue*. Attempt 1 began the task-relative clock before the coroutine issuing `hass.services.async_call()` had actually been scheduled. Under a 32-task wave, event-loop queueing could therefore consume part of the 100 ms decision window before Home Assistant received ACT1. This explains both the replica-1 source qualification failure and spurious misses in the 35 ms no-feedback-shift control.

2. **Native event drain.** Attempt 1 sliced `EVENT_CALL_SERVICE` and `EVENT_STATE_CHANGED` after only `await asyncio.sleep(0)`. Home Assistant dispatches event callbacks as tracked jobs; one loop turn is not a completeness barrier. Replica 0's early per-mode slices therefore undercounted some events. Crucially, the final raw HA event stream retained in the same artifact contains the missing events. For example, runs whose early slice undercounted ACT2/state events have exact final run-id counts after the experiment completed. The correction is to use Home Assistant's own `await hass.async_block_till_done()` before native-event slicing.

### Allowed correction

The scientific protocol remains unchanged:

- 100 ms deadline;
- source/target delays 35/180 ms;
- 128 tasks;
- wave size 32;
- wave period 300 ms;
- 6 decisive trials per runner;
- 2 independent runner replicas;
- unchanged R0/R1/R2 semantics;
- exact 256/256/384 service-call conservation;
- exact 256 experiment-owned state changes per mode/trial;
- exact 1.5x R2/R1 workload;
- unchanged negative controls and certificate thresholds.

Only implementation synchronization is corrected:

- operation-relative clocks begin immediately before the actually scheduled Home Assistant `async_call`, not at coroutine creation;
- deadlines are absolute monotonic deadlines derived from that issue clock;
- R0 sleeps to an absolute source-relative issue deadline rather than adding scheduler delay;
- Home Assistant's `async_block_till_done()` is the event-completeness barrier before accounting.

Attempt 1 is retained permanently and must not be cited as a valid E3c promotion run.

### Correction commit

The synchronization-only correction was atomically committed as `1aa7a7e6425ea4fec3d6b479df83ea938d1e17a1`, directly parented on the invalid attempt's frozen execution commit. The preregistered scientific parameters and promotion thresholds were not changed.


## No-shift causal autopsy and canonical observer correction

- Eight minimally perturbative v3 differential-autopsy runners were completed across workflow runs `33941999055` and `33942017584`.
- Frozen observer no-shift MISS tasks: 125.
- Same-task entity-indexed Home Assistant callback already visible by the identical 100 ms deadline: 116/125 (92.8%).
- Remaining state-set-late cases under frozen observer load: 9/125 (7.2%).
- Root cause: per-task global plain listeners were Home Assistant Executor jobs, creating O(N^2) fanout and cross-thread asyncio Future mutation; tail cases additionally exhibited observer self-interference.
- Canonical correction: entity-indexed `async_track_state_change_event` + explicit `HassJobType.Callback` + strict callback-timestamp deadline test.
- Scientific protocol and all promotion thresholds remain unchanged.
- This correction is not a promotion result; a fresh replicated run is required.
