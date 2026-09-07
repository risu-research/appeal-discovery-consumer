# Gate S2-Q3 — Boundary-Complete Source Qualification Failure Seal

Status: **FROZEN COMPLETE SCIENTIFIC FAILURE.**

Q3 executed the frozen P5 protocol using the exact Q2 source runner. The old `p99 <= 80 ms` slack proxy had no promotion role. All three fresh source screening rounds completed and were structurally valid, but no candidate achieved complete visibility of every expected observation by the inherited 100-ms evidence boundary.

## Authority

- P5 protocol: `a21192a7214c2e8eb6d2a4940775172a65b3e1e8`
- Q3 execution: `0f5030358f3c71ba52d852b38987fc4f767fded7`
- execution tree: `45178efdcc00e25013c35452289bcad16113cfd8`
- workflow run: `34166084457`
- workflow job: `101877267114`
- artifact: `10034219737`
- artifact SHA-256: `7342d81c328d54b31e6049ac2ae32c6a30cb9a14ca3a22e6c6676ce3187f2932`

## Result

| Wave | Rows | Visible by 100 ms | p99 ms (descriptive) | max ms | Qualification |
|---:|---:|---:|---:|---:|---|
| 16 | 576 | 575/576 | 86.185997 | 124.458249 | FAIL |
| 8 | 576 | 559/576 | 123.796275 | 124.852318 | FAIL |
| 4 | 576 | 574/576 | 82.226334 | 123.502302 | FAIL |

All candidate rows were structurally valid and all tasks completed by the 1000-ms timeout. The failure was specifically the frozen boundary-completeness condition.

Therefore:

```text
W_star_screen = null
holdout_admitted = false
holdout_rows = 0
D_star_ms = null
shifted_target_executed = false
```

## Strategic interpretation

Q3 falsifies the idea that removing the non-semantic 80-ms p99 slack alone is enough to make the stochastic-mixed capstone robust on this hosted live path. Even under the actual 100-ms boundary-completeness criterion, every candidate experienced at least one deadline miss.

This does **not** mean ReplayMark requires a different theorem, nor does it justify moving the deadline after seeing the result. It means the experimental plan was relying on transport/runtime timing noise to simultaneously provide (a) a perfectly clean source reference and (b) a natural mixed target boundary. That coupling is unnecessary for the paper's core claim.

The stronger next design is to stop using stochastic transport jitter as the mechanism that creates the mixed workload. Instead, prospectively freeze a **single heterogeneous target configuration** containing both unchanged/supported and changed/unsupported target units, balanced independently of the policy outcome. ReplayMark must not receive the hidden target class; it must decide solely from the same runtime evidence and frozen contract.

This preserves the real research question—selectively retain the historical decisions that remain semantically supported—while removing the fragile requirement that a hosted MQTT tail happen to create the desired mixture.

## Anti-repair

- Q3 cannot be rerun until favorable.
- No wave 2/1 is inserted into this generation.
- The 100-ms deadline is not retuned inside this generation.
- No D* is derived from the failed screening.
- The target remains unobserved.
- Any heterogeneous-target continuation is a new preregistered protocol generation, not a repair of Q3.
