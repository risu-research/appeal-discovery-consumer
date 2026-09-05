# Canonical Paper Results Table

> Machine-generated from `PAPER_RESULTS_MANIFEST.json`. Do not hand-edit.

| Claim | Canonical evidence | Result | Status |
|---|---|---|---|
| Timing fidelity is not controller-semantic fidelity | E3b / E3c / N1 | E3b R1 support failure 12/12 (100%); E3c R1 1536/1536 (100%); N1 R1 12/12 (100%); semantic R2 support failure is 0 in all three | CLOSED |
| Replay semantics can change benchmark workload | E3b / E3c | E3b 512→768 PUBLISH = 3/2 (= 1.5×); E3c 256→384 native calls = 3/2 (= 1.5×) | CLOSED |
| Operation identity is not action identity | N2 | TV_operation=0; TV_action=1; same `climate.set_preset_mode`, `home`→`away` variant | CLOSED |
| Raw feedback difference is not replay invalidity | N2b | raw TV=1; quotient TV=0; action TV=0; target replay support failures 0/12 (0%) | CLOSED |

N1 runner timing shifts are deliberately not averaged in the canonical layer: replica 0 = 35.248967 ms; replica 1 = 35.1785321666667 ms.
