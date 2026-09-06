# ReplayMark N2 Horizon Runtime Realization — promotion record

Status: **PROMOTED**

This record freezes the successful theory→runtime closure for the claim-predictive horizon witnesses. It is downstream of the preregistration and the explicitly frozen measurement correction; it does not redefine either scientific pair or prediction.

## Authoritative execution

- GitHub Actions run: `34010550012`
- Scientific execution head: `a4fcc99c18c28138218fb553cd4a95fa182cabec`
- Workflow: `ReplayMark N2 Horizon Runtime Realization`
- Promoted artifact: `replaymark-n2-horizon-runtime-promoted`, artifact id `9982336698`
- Artifact ZIP SHA-256: `7a594987991d407b0702411b70859d5d9eecb4034f43c8908f44e9cf6299a098`
- Aggregate JSON SHA-256: `60c2cf2ad7e5ac24b7af74199877d59812e7d214900a1982dba7395703467f51`
- Aggregate checksum-manifest SHA-256: `a485b2f154467f2f74d3ccb83ddde0933f5515abf6bbf1395cef45506d519a2a`
- Home Assistant image: `ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293` (Core 2026.9.0)
- Pinned external blueprint SHA-256: `16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443`
- Qualified Better Thermostat component tree was identical across both runners.

## Replicated result

The final aggregate contains **48 fresh Home Assistant runtime cells**: two independent hosted runners × six trials × two histories × two depth tests.

Every cell satisfies the preregistered semantic prediction and the corrected independent raw-event validator.

| Test | History | Cells | Exact live output sequence |
|---|---|---:|---|
| depth 1 | motion off | 12 | `AWAY -> HOME` |
| depth 1 | motion on | 12 | `AWAY -> COMFORT` |
| depth 2 | motion off | 12 | `NO_ACTION -> HOME` |
| depth 2 | motion on | 12 | `NO_ACTION -> COMFORT` |

Therefore the model-derived N2b shortest witness is realized exactly in live Home Assistant:

- current decision: both histories emit `AWAY`;
- shortest admitted suffix: `presence_toggle`;
- next decision: `HOME` versus `COMFORT`.

The independently discovered depth-2 witness is also realized exactly:

- step 1, `presence_toggle`: both histories emit `NO_ACTION` and remain at `sleep`;
- step 2, `night_toggle`: `HOME` versus `COMFORT`.

The final aggregate promotion gates all passed: exact image/version, exact controller hash, same ownership-component tree, both producer reports promoted, both independent validators passed, all four conditions had 12 cells, all four output sequences were exact, and all producer rows passed.

## Measurement-correction audit trail

The first preregistered run `34010261833` already produced all predicted semantic sequences on both replicas, but its independent validator rejected a microstep assertion that treated a state-registry read from inside `EVENT_CALL_SERVICE` as the pre-handler thermostat preset. Raw retained events showed that this listener observes the already-mutated registry state in Home Assistant 2026.9.0. The scientific predictions, controller, histories, continuations, trial counts, runner count, and producer semantic gates were not changed. The correction was frozen before rerun in `N2_HORIZON_RUNTIME_MEASUREMENT_CORRECTION.md`; the corrected independent validator uses native climate `EVENT_STATE_CHANGED` old/new preset transitions instead. Run `34010550012` then passed both independent validators and the replicated aggregate gate.

## Scientific claim licensed by this promotion

> Under the pinned external Better Thermostat controller, frozen N2/N2b configuration, qualified ownership boundary, and Home Assistant Core 2026.9.0, the exact shortest distinguishing continuations predicted by the claim-predictive model are realized in live middleware execution: local AWAY equality splits after one `presence` continuation into HOME versus COMFORT, and an independently discovered pair remains equal for one continuation before splitting after the second.

This result does not claim deployed-home prevalence, physical-device behavior, optional boost/eco/activity configurations, writeback behavior, arbitrary external preset changes, or novelty of the underlying automata minimization machinery.
