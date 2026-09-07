# Gate S2-F — Heterogeneous-Target Falsification Audit Result Seal

Status: **FROZEN COMPLETE PASS.**

S2-F adversarially re-audited the immutable first-complete P6 capstone without starting a new target or rerunning the live workload. The audit consumed only the exact P6 artifact from workflow run `34168034341`, artifact `10034798750`, ZIP SHA-256 `1319c41908d511ca9e8976973801350aab593199038b82752d8e4e7c78d0ecdb`.

## Authority

- P6 result seal: `60c444f32f98c9ee9ef42c8b06395ebf4ed9a902`
- corrected S2-F audit: `91f217c2db79f84b269e4a350d86bcc82d302ac5`
- audit tree: `d570097d975ba1d60fa2b3819e4bf7f6d1351f17`
- audit workflow run: `34169373685`
- audit workflow job: `101886605891`
- audit artifact: `10035196799`
- audit artifact SHA-256: `2159054f1b84308e8f0f5d32227dea03d57f2fa41e04f8ba90f2ab354f37ace3`
- audit artifact size: 599,251 bytes
- P6 live raw SHA-256: `efc111166330a71634b40a190e046b5154c21f44096cfb375c6850c7975f7b80`

The earlier S2-F attempt `31cc0d77b9fbc5c389f30e04e0a95fa58aafa276` / run `34168431916` failed before fetching the P6 artifact because its source-string import self-check matched its own forbidden-token literals. That attempt is preserved at `replaymark-dev-s2f-selfscan-preflight-failure`. It is development history, not an audit result.

## Independent audit boundary

The corrected second literal auditor uses only Python standard-library imports. It imports no ReplayMark production code, AgentMark code, Paho code, or original independent oracle. Its own import graph is checked through the Python AST rather than a source-string grep.

The workflow also verifies:

- exact parent is the frozen P6 result seal;
- only the four declared S2-F files were added;
- no new target or broker workload is started;
- exact P6 artifact ID, workflow run, and ZIP SHA are pinned;
- every internal P6 artifact file passes the original `SHA256SUMS` manifest before evaluation.

## Second-literal result

Every adversarial check passed. Failure arrays were empty for semantic recomputation, execution reconstruction, phase ordering, B-side effects, action-call cardinality, and foreign sink calls.

The independently recomputed result was exactly:

| Policy | Oracle-safe | Oracle-unsafe | Actually executed |
|---|---:|---:|---:|
| Always-Admit | 186 | 198 | 384 |
| Always-Block | 191 | 193 | 0 |
| ReplayMark | 188 | 196 | **188** |

Hidden target-class recomputation was also identical to the frozen first verifier:

```text
REFERENCE: 565 safe, 11 unsafe
SHIFTED:     0 safe, 576 unsafe
```

ReplayMark's actual execution set was again exactly equal to the second auditor's literal safe set.

## Strong hidden-class falsification

The second auditor reconstructed four tasks assigned to ReplayMark that were hidden-class `REFERENCE` but nevertheless unsafe under the actual frozen observation evidence:

```text
(trial 2, task 131)
(trial 2, task 133)
(trial 2, task 147)
(trial 4, task 41)
```

A class-only rule that admitted every `REFERENCE` task would therefore have executed four unsafe historical actions on the ReplayMark arm. ReplayMark executed none of them.

This falsifies the explanation that ReplayMark merely followed the hidden target partition. Its admitted set tracks the actual semantic evidence boundary instead.

## S2 closure

S2 is now closed as a successful selective-reuse capstone:

```text
safe history retained by ReplayMark       = all 188 safe assigned decisions
unsafe historical executions by ReplayMark = 0 / 196
unnecessary ReplayMark blocks               = 0
Always-Admit unsafe executions             = 198
Always-Block safe decisions discarded      = 191
new live execution during S2-F             = 0
fallback                                    = ABSENT
regeneration                                = ABSENT
```

The Q1/Q2/Q3 stochastic source-calibration line remains immutable failed evidence and is retired rather than repaired. P6 replaced its unnecessary dependence on hosted transport jitter with a prospectively frozen heterogeneous target whose hidden class remained blind to ReplayMark.

This seal does not claim cross-process exactly-once, broker-delivery exactly-once, fallback quality, regeneration quality, or latency speedup.
