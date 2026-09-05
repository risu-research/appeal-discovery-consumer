from __future__ import annotations

from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]
PART1 = ROOT / "agentmark_e3c_ha" / "home_assistant_ecological.part1.pyfrag"
PART2 = ROOT / "agentmark_e3c_ha" / "home_assistant_ecological.part2.pyfrag"
PART3 = ROOT / "agentmark_e3c_ha" / "home_assistant_ecological.part3.pyfrag"
HISTORY = ROOT / "agentmark_e3c_ha" / "EXECUTION_HISTORY.md"
REPORT = ROOT / "agentmark_e3c_ha" / "NO_SHIFT_CAUSAL_AUTOPSY.md"

old = PART1.read_text()
text = old

old_import = "from homeassistant.core import Context, CoreState, Event, HomeAssistant\n"
new_import = (
    "from homeassistant.core import Context, CoreState, Event, HassJobType, HomeAssistant, callback\n"
    "from homeassistant.helpers.event import async_track_state_change_event\n"
)
if text.count(old_import) != 1:
    raise SystemExit("precondition failed: exact HA core import signature not found once")
text = text.replace(old_import, new_import, 1)

old_install = "    def install(self) -> None:\n        def on_call(event: Event) -> None:\n"
new_install = "    def install(self) -> None:\n        @callback\n        def on_call(event: Event) -> None:\n"
if text.count(old_install) != 1:
    raise SystemExit("precondition failed: HALab on_call signature not found once")
text = text.replace(old_install, new_install, 1)

old_on_state = "\n        def on_state(event: Event) -> None:\n"
new_on_state = "\n        @callback\n        def on_state(event: Event) -> None:\n"
if text.count(old_on_state) != 1:
    raise SystemExit("precondition failed: HALab on_state signature not found once")
text = text.replace(old_on_state, new_on_state, 1)

start = text.find("async def wait_for_on_until(\n")
end = text.find("\n\nasync def wait_for_on(\n", start)
if start < 0 or end < 0:
    raise SystemExit("precondition failed: wait_for_on_until boundaries not found")

canonical = '''async def wait_for_on_until(
    hass: HomeAssistant,
    entity_id: str,
    deadline_ns: int,
) -> tuple[bool, int | None]:
    """Observe one entity through HA's indexed callback path to an absolute deadline.

    The previous implementation registered one global EVENT_STATE_CHANGED listener
    per task. Because those plain ``def`` listeners were classified by Home
    Assistant as Executor jobs, a 32-task wave generated O(N^2) executor fanout
    and cross-thread ``asyncio.Future.set_result`` calls. This observer uses Home
    Assistant's entity-indexed helper and explicit Callback job type instead.

    A callback that executes after the absolute deadline is a MISS even if
    asyncio timeout scheduling happens to resume it before the timeout waiter.
    """
    now = now_ns()
    state = hass.states.get(entity_id)
    if state is not None and state.state == "on":
        return (now <= deadline_ns), (now if now <= deadline_ns else None)

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[int] = loop.create_future()

    @callback
    def listener(event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is not None and new_state.state == "on" and not fut.done():
            fut.set_result(now_ns())

    unsub = async_track_state_change_event(
        hass,
        entity_id,
        listener,
        job_type=HassJobType.Callback,
    )
    try:
        # Close the state-check / listener-registration race without leaving the
        # event loop or creating executor work.
        state = hass.states.get(entity_id)
        if state is not None and state.state == "on" and not fut.done():
            observed_ns = now_ns()
            if observed_ns <= deadline_ns:
                fut.set_result(observed_ns)
            else:
                return False, None

        remaining_s = max(0.0, (deadline_ns - now_ns()) / 1_000_000_000.0)
        if remaining_s <= 0.0:
            return False, None
        try:
            event_ns = await asyncio.wait_for(fut, timeout=remaining_s)
        except TimeoutError:
            return False, None

        # Strict absolute-deadline semantics. This guard matters if the event
        # loop resumes both a late callback and the timeout after a scheduler
        # stall; callback ordering must not turn a post-deadline event into a hit.
        if event_ns > deadline_ns:
            return False, None
        return True, event_ns
    finally:
        unsub()
'''

text = text[:start] + canonical + text[end:]

if text == old:
    raise SystemExit("no source change produced")
if "hass.bus.async_listen(EVENT_STATE_CHANGED, listener)" in text:
    raise SystemExit("forbidden legacy global decision listener remains")
if "async_track_state_change_event(" not in text or "job_type=HassJobType.Callback" not in text:
    raise SystemExit("canonical indexed callback observer not materialized")

PART1.write_text(text)

report = '''# E3c No-Shift Failure — Task-Level Causal Autopsy

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
'''
REPORT.write_text(report)

marker = "## No-shift causal autopsy and canonical observer correction"
history = HISTORY.read_text()
if marker in history:
    raise SystemExit("history marker already present")
history += f'''\n\n{marker}\n\n- Eight minimally perturbative v3 differential-autopsy runners were completed across workflow runs `33941999055` and `33942017584`.\n- Frozen observer no-shift MISS tasks: 125.\n- Same-task entity-indexed Home Assistant callback already visible by the identical 100 ms deadline: 116/125 (92.8%).\n- Remaining state-set-late cases under frozen observer load: 9/125 (7.2%).\n- Root cause: per-task global plain listeners were Home Assistant Executor jobs, creating O(N^2) fanout and cross-thread asyncio Future mutation; tail cases additionally exhibited observer self-interference.\n- Canonical correction: entity-indexed `async_track_state_change_event` + explicit `HassJobType.Callback` + strict callback-timestamp deadline test.\n- Scientific protocol and all promotion thresholds remain unchanged.\n- This correction is not a promotion result; a fresh replicated run is required.\n'''
HISTORY.write_text(history)

# Compile the exact concatenation consumed by the E3c workflow.
combined = ROOT / ".e3c_canonical_compile_check.py"
combined.write_text(PART1.read_text() + PART2.read_text() + PART3.read_text())
try:
    py_compile.compile(str(combined), doraise=True)
finally:
    combined.unlink(missing_ok=True)

print("E3c canonical observer migration prepared and compile-checked")
