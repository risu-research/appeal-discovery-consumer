# AgentMark — Natural Controller Gate

Status: **design frozen before corpus outcomes** on `agentmark-theory-lock`.

Purpose: remove the strongest remaining reviewer objection — that E3b/E3c use a controller deliberately constructed to cross an ACT2/VERIFY branch — without turning the paper into a collection of anecdotes or cherry-picked vulnerable automations.

## 1. Scientific question

Do independently authored pervasive-system controllers exhibit the decision structure predicted by AgentMark, and does the locked AgentMark classification predict replay validity when their feedback conditions are changed?

The corpus is therefore a **prediction test of the theory**, not a search for more examples where R2 wins.

## 2. Unit of analysis

The primary unit is an externally authored executable controller specification, preferably a Home Assistant automation/blueprint because E3c already qualifies the actual HA middleware substrate.

Sensor-only traces without controller semantics are not sufficient for this gate. We do not infer a policy from CASAS-style ambient traces and then call the result an external controller.

## 3. Fail-closed source inclusion

A candidate is eligible only if all of the following are satisfied before replay outcomes are inspected:

- source is public and commit-pinned;
- source contains executable controller logic rather than prose-only behavior;
- controller branch/condition semantics are supplied by the source itself or executed by the native HA engine;
- experiment bindings may replace concrete devices with deterministic virtual entities/services, but may not rewrite branch logic;
- semantic action identity is derivable mechanically from the executable action or from a predeclared adapter rule;
- unsupported Jinja/templates/device integrations are excluded with a machine-readable reason instead of being manually interpreted;
- no candidate is included or excluded because AgentMark happens to classify it SAFE or UNSAFE.

## 4. Two-stage design prevents cherry-picking

### Stage A — corpus classification

Run the importer/classifier on every syntactically eligible controller. Record, without target perturbation outcomes:

- number of controller decision points;
- feedback alphabet/condition structure exposed by the adapter;
- decision-equivalence classes under each declared projection;
- `eta` / feedback sensitivity;
- whether distinct branches differ by operation, action variant, target class, multiplicity, or only timing;
- unsupported constructs and exclusion reason.

This stage answers a prevalence/structure question: how common are feedback-insensitive, operation-sensitive, and parameter-sensitive controller decisions in independently authored pervasive automations?

### Stage B — causal replay validation

Select validation cases by a predeclared stratified rule over Stage-A classes, not by whether a replay failure was observed. For each selected case, construct source and target feedback conditions that stay within or cross the already-classified decision classes, then compare R0/R1/R2 using the native HA automation/script engine where feasible.

The theory predicts the direction before execution:

- **same decision class:** semantic workload should remain unchanged at the declared projection;
- **different class, overlapping support:** workload distribution may shift without a zero-support violation;
- **different class, disjoint support for recorded event:** rigid/timing replay should produce a support failure;
- **same operation, different semantic variant:** operation projection may call the replay valid while action projection correctly distinguishes the branch.

## 5. Required controller classes

The corpus should cover qualitatively distinct controller structures rather than many near-duplicates:

1. **Feedback-insensitive negative class** — feedback changes but projected action does not.
2. **Event-response branch** — user/device event selects a different subsequent action.
3. **State-priority policy** — current states/attributes select among prioritized actions or parameter variants.
4. **Timeout / retry / wait branch** — missing feedback inserts, removes, or changes work.
5. **Concurrency/mode semantics** — restart/queued/parallel behavior changes which action sequence remains live.
6. **Same-operation / different-variant** — service identity is unchanged but target or consequential parameters differ.
7. **Multiplicity/path change** — target feedback changes number or sequence of native actions, connecting directly to the E3b/E3c benchmark-workload consequence.

A paper-quality corpus does not require equal counts in every class, but any absent class must be reported as absent rather than synthesized after the fact.

## 6. Seed candidates (not yet qualified evidence)

These are discovery seeds only. Presence in this list does not imply inclusion in the final corpus.

### HA-OFFICIAL-MOTION-LIGHT

- repository: `home-assistant/core`
- commit: `0cb25fe4727b5466743285f048eb6aa75fd02bbb`
- path: `homeassistant/components/automation/blueprints/motion_light.yaml`
- author: Home Assistant
- structure hint: motion trigger -> `light.turn_on` -> wait for no motion -> delay -> `light.turn_off`
- likely class: wait/state feedback and restart-mode behavior
- qualification status: `seed_unqualified`

### HA-ACTIONABLE-NOTIFICATION

- repository: `maxi1134/Home-Assistant-Config`
- commit: `280f3424aa4fa54b2a11830ab4cc277c78d2a647`
- path: `blueprints/automation/McDAlexander/actionable_notifications_for_android_with_cam.yaml`
- structure hint: wait for `mobile_app_notification_action`, then choose `action1`, `action2`, or `action3`, each executing a distinct externally supplied action sequence
- likely class: event-response branch
- qualification status: `seed_unqualified`

### HA-BETTER-THERMOSTAT-LEAN

- repository: `n3roGit/MyHomeAssistantMods`
- commit: `57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f`
- path: `automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml`
- structure hint: boost/night/presence/eco/activity/motion priority policy chooses `boost`, `sleep`, `away`, `eco`, `activity`, `comfort`, or `home` preset; current preset also gates writeback behavior
- likely class: state-priority and same-operation/different-variant
- qualification status: `seed_unqualified`

### HA-RING-KEYPAD

- repository: `ImSorryButWho/HomeAssistantNotes`
- commit: `375e1d0501f676e3f52937cb4fd84ddfaef6a549`
- path: `keypad_blueprint.yaml`
- structure hint: keypad/alarm event-driven controller
- likely class: event-response / state-dependent alarm action
- qualification status: `seed_unqualified`

### HA-FRIGATE-NOTIFICATION

- repository: `arsaboo/homeassistant-config`
- commit: `2a0376e3dca1a6d948f8f09b580f067d42ab8b0c`
- path: `blueprints/automation/hunterjm/frigate_0.10_notification.yaml`
- structure hint: Frigate event/notification controller with waits and conditional notification behavior
- likely class: event-response / wait / multiplicity
- qualification status: `seed_unqualified`

## 7. Adapter contract

The adapter should extract semantics from native executable structure and produce an AgentMark controller representation. It must not silently understand arbitrary application meaning.

For Home Assistant the minimal safe adapter surface is:

- `choose` / conditions;
- `wait_for_trigger` and timeout outcome;
- explicit service/action calls;
- explicit static targets;
- explicit scalar service-data values that can be canonicalized without evaluating arbitrary external state;
- script/automation control-flow primitives whose behavior is implemented by the HA engine.

For an action the adapter emits:

- `operation`: native service/action identity, e.g. `climate.set_preset_mode`;
- `target_class`: stable domain/class if mechanically known;
- `variant`: canonical consequential arguments that are statically and unambiguously specified, e.g. `preset_mode=away`;
- controller successor state/control location.

If `variant` depends on a template whose value cannot be established from the controlled experiment inputs, the case is not guessed. It is either executed under native HA with the realized action captured, or excluded from static classification.

## 8. Primary evaluation metrics

The strongest paper is not built around "how many controllers fail." It is built around **prediction accuracy and explanatory compression**.

For each validated decision point compare the locked AgentMark prediction to native replay behavior:

- decision-class crossing predicted / observed;
- recorded-event target support predicted / observed;
- projected workload shift predicted / observed;
- R0/R1/R2 semantic validity;
- native action conservation/context lineage where the substrate exposes it;
- action projection versus operation projection for same-operation variants.

A null result in one class is scientifically acceptable and must not cause the inclusion rule to change.

## 9. Strongest possible paper-facing result

The ideal result is not "all natural controllers are vulnerable." A more credible and more general result is a partition such as:

- some controllers are provably feedback-insensitive at the chosen projection, and replay remains valid despite feedback shift;
- some cross decision classes but retain overlapping support, producing distributional workload drift;
- some cross into support-disjoint branches, reproducing the E3b/E3c hard failure;
- some look identical at operation level but diverge at action/parameter level.

If native experiments follow these theory-derived classes, AgentMark explains **when replay is safe and when it is not**, rather than merely detecting a pathology it was designed to create.

## 10. Gate to full causal corpus execution

Do not begin a large natural-controller replay sweep until:

- theory CI is green;
- action-identity regression is green;
- importer inclusion/exclusion decisions are emitted before target perturbation results;
- at least the first two seed controllers can be parsed/executed without rewriting their branch logic;
- corpus manifest stores repository, commit, path, source hash, qualification result, and exclusion reason.

Once those hold, the natural-controller gate becomes the highest-value empirical next step for PerCom.
