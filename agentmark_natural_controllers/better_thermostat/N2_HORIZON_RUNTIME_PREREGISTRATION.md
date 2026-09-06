# ReplayMark N2 Horizon Runtime Realization — preregistration

Status: **FROZEN BEFORE RUNTIME EXECUTION**

Purpose: directly falsify the strongest new `q_{C,H}` prediction in a real Home Assistant 2026.9.0 runtime using the already-pinned external Better Thermostat blueprint and the already-qualified Better Thermostat device-ownership boundary. This is a theory→middleware closure experiment, not a new domain expansion.

## Frozen upstreams

- Base runtime branch ancestry: `agentmark-n2b-decision-equivalence` at `1a38808a2c83fb6cf68091beb0a244eec3dab9ec`.
- Home Assistant image tag/digest contract: `ghcr.io/home-assistant/home-assistant:2026.9.0` resolved and required to equal `ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293`.
- External controller: `n3roGit/MyHomeAssistantMods@57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f`, `automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml`, SHA-256 `16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443`.
- Better Thermostat ownership component: `KartoffelToby/better_thermostat@b86561f61e5ba1259fc63e590f4847e9ac743d7f`, version `1.9.2`, manifest SHA-256 `710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28`.
- Frozen theory prediction source: `replaymark-theory-sufficiency` result freeze `83ca49fd6f78fd7ba4a057e8374e461fea693c16`; the claim-state gate predicts the N2b shortest distinguishing suffix `presence_toggle` at depth 1 and an independently discovered depth-2 suffix `presence_toggle, night_toggle`.

## Claim and projection

The benchmark claim is the consequential preset service action emitted by the pinned controller. The projected output alphabet for this experiment is:

- `SET_AWAY`
- `SET_HOME`
- `SET_COMFORT`
- `SET_SLEEP`
- `NO_ACTION`

`NO_ACTION` is consequential because the blueprint suppresses `climate.set_preset_mode` when current preset already equals the controller-selected target.

## Primary falsification test A — N2b depth 1

Each fresh runtime starts with current preset `sleep`, night `off`, presence `on`, and motion fixed for the entire trial.

Two histories are realized independently:

- A: motion `off`
- B: motion `on`

Frozen trigger 0 is identical: `presence on -> off`.

Prediction at the current decision (`H=0`): both histories issue exactly one `climate.set_preset_mode(away)` action and end with current preset `away`.

Frozen distinguishing continuation: `presence off -> on`.

Prediction at depth 1:

- A emits exactly one new `climate.set_preset_mode(home)` action;
- B emits exactly one new `climate.set_preset_mode(comfort)` action.

The shortest-witness claim passes only if the first decision is equal and the one-trigger continuation separates the two histories exactly as predicted.

## Primary falsification test B — independently discovered depth 2

Each fresh runtime starts with current preset `sleep`, night `on`, presence `off`, and motion fixed for the entire trial.

Two histories are realized independently:

- A: motion `off`
- B: motion `on`

Frozen continuation step 1: `presence off -> on`.

Prediction: because night mode outranks presence and motion and current preset is already `sleep`, both histories emit `NO_ACTION`; the climate preset remains `sleep`.

Frozen continuation step 2: `night on -> off`.

Prediction:

- A emits exactly one `climate.set_preset_mode(home)` action;
- B emits exactly one `climate.set_preset_mode(comfort)` action.

The depth-2 claim passes only if there is no consequential service action after step 1 and the separation appears only after step 2.

## Replication and ordering

- Two independent GitHub-hosted runners (`replica=0,1`).
- Six fresh Home Assistant trials per history per depth test on each runner.
- Each trial creates a fresh Home Assistant runtime and fresh automation instance.
- Condition order is deterministically alternated by trial index to avoid a fixed A-before-B order becoming a hidden run-level confound.
- Task/event rows are not treated as independent statistical replicates; the semantic predictions are deterministic all-cells assertions.

## Measurement contract

The producer must retain, for every transition:

1. pre-trigger feedback and current-preset snapshot;
2. relevant Home Assistant `EVENT_STATE_CHANGED` witnesses;
3. every consequential `EVENT_CALL_SERVICE` for `climate.set_preset_mode`, including rendered service data, action identity, feedback snapshot, preset before issue, and event context;
4. post-step feedback/current-preset snapshot;
5. monotonic timestamps sufficient to establish state-transition-before-service ordering.

The observer is passive: it must never issue a control action.

## Promotion gates

Promotion requires **all** of the following on both independent runners:

1. exact pinned HA image digest, blueprint hash, Better Thermostat component commit/version/tree;
2. upstream ownership qualification occurs before scientific outcome and integration internal setup remains uninvoked, matching N2/N2b;
3. no consequential action occurs during state seeding or automation installation;
4. depth-1 trigger 0 produces `AWAY` in all A/B cells;
5. depth-1 continuation produces `HOME` for A and `COMFORT` for B in all cells;
6. depth-2 step 1 produces `NO_ACTION` in all A/B cells and leaves preset `sleep`;
7. depth-2 step 2 produces `HOME` for A and `COMFORT` for B in all cells;
8. no extra `climate.set_preset_mode` actions occur within a trial beyond the predicted sequence;
9. native state-change and service-issue ordering is consistent with the frozen continuation sequence;
10. an independent validator, written separately from the producer checks, reconstructs every predicted output sequence from raw retained events and agrees with the producer;
11. aggregate requires both runner capsules to pass their checksum manifests and the same all-cells semantic predictions.

Any violation is `NOT_PROMOTED`; no threshold or protocol parameter may be changed after observing runtime outcomes.

## Interpretation if promoted

Promotion supports only this statement:

> The exact shortest distinguishing continuations predicted from the pinned external controller model are realized in Home Assistant 2026.9.0 under the frozen N2/N2b configuration and qualified device-ownership boundary.

It does not establish prevalence in deployed homes, optional boost/eco/activity configurations, writeback behavior, arbitrary external preset changes, physical-device effects, or a new state-minimization theorem.
