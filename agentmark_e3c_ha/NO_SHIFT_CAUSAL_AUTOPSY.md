# E3c No-Shift Failure — Task-Level Causal Autopsy

Status: **ROOT CAUSE ESTABLISHED; SCIENTIFIC PROTOCOL UNCHANGED**

## Question

Why did the preregistered no-feedback-shift negative control intermittently report MISS even though source and target both used the same nominal 35 ms ACT1 delay under a 100 ms controller deadline?

## Evidence before instrumentation

Across four corrected pre-autopsy runners, 57 no-shift MISS tasks were retained in raw artifacts. Every one of those 57 tasks completed ACT1 service execution before the 100 ms deadline, every corresponding state change eventually arrived, and Home Assistant Context lineage matched the causative ACT1 call. Misses appeared as contiguous blocks or suffixes inside 32-task waves rather than independent device failures.

## Code-path finding

The frozen decision observer registered one global `EVENT_STATE_CHANGED` listener per task using a plain Python `def`. Home Assistant 2026.9.0 classifies an unmarked synchronous HassJob as `Executor` and runs it through the default executor. With 32 simultaneous task monitors, each state event fan-outs across the active global listeners, producing O(N^2) observer jobs. The worker-thread listener also called `asyncio.Future.set_result()` on a future owned by the event loop.

Home Assistant's own `async_track_state_change_event` helper exists specifically to route state changes by entity id instead of scanning a long global listener list and creating irrelevant jobs.

## Differential autopsy

Two minimally perturbative v3 run sets were executed, each with four independent GitHub-hosted runners (8 runners total). The frozen observer remained authoritative for the base result. In parallel, each task received a shadow observer using Home Assistant's entity-indexed `async_track_state_change_event` path with explicit `HassJobType.Callback`. The shadow callback timestamp was compared directly to the same absolute 100 ms deadline.

Run sets:

- `33941999055` — four v3 runners at commit `3822da08a865164e8a479441e9b00148e30123a1`.
- `33942017584` — four v3 runners at commit `d252e45dafda5b175e82d9c5046241424dbf3502`.

Across the eight runners, the frozen observer produced **125 no-shift MISS tasks**. Of these:

- **116 / 125 (92.8%)** were direct false misses: the entity-indexed HA callback had already executed by the 100 ms deadline while the frozen global-executor observer reported MISS.
- **9 / 125 (7.2%)** had ACT1 state creation itself pushed beyond the deadline under the frozen observer load, consistent with observer self-interference rather than a changed feedback law.
- Some runners produced zero frozen no-shift misses and independently reached the full base `PROMOTED` gate, demonstrating that the old negative-control failure was not a stable ecological property.

The earlier v1 autopsy deliberately remains non-decisive because its shadow observer added another global-listener fanout and measurably perturbed state timing. v2 identified an R2 association ambiguity: a VERIFY after decision MISS can create a second wait for the same entity. v3 fixed that association *before execution* by selecting the observation with the earliest absolute deadline, which uniquely identifies the 100 ms decision monitor without using its outcome.

## Root-cause verdict

`NO_SHIFT_FAILURE = MEASUREMENT_OBSERVER_ARTIFACT + SELF_INTERFERENCE`

The evidence does **not** support interpreting the no-shift misses as a Home Assistant ecological change in the underlying 35 ms feedback law.

## Allowed correction

No scientific parameter or promotion criterion is relaxed. The correction is restricted to observation mechanics:

1. replace per-task global `EVENT_STATE_CHANGED` listeners with Home Assistant's entity-indexed `async_track_state_change_event` helper;
2. mark the listener explicitly as `HassJobType.Callback`, keeping it on the event-loop callback path;
3. eliminate cross-thread `Future.set_result` use;
4. enforce `event_callback_monotonic_timestamp <= absolute_deadline` even if timeout/callback scheduling resumes out of intuitive order after a stall;
5. mark the passive HALab accounting listeners as Home Assistant callbacks so measurement itself does not inject unnecessary executor jobs.

Frozen scientific quantities remain unchanged: 100 ms deadline, 35/180 ms source/target delays, 128 tasks, wave size 32, 300 ms wave period, six decisive trials per runner, two independent promotion replicas, R0/R1/R2 semantics, native event conservation, exact 1.5x R2/R1 work, negative controls, certificate epsilon/confidence, and all promotion gates.

## Promotion rule after correction

The autopsy does not itself promote E3c. Promotion requires a fresh replicated E3c execution on the canonical observer implementation, independent host-side validation, exact native accounting/Context lineage, both negative controls, and every preregistered gate unchanged.
