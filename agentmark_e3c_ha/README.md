# AgentMark E3c — Home Assistant Ecological Replication

E3c transfers the already-promoted E3b replay ladder onto **Home Assistant Core 2026.9.0**.

The key design choice is to avoid a Home-Assistant-shaped simulator. The experiment runs inside the official Home Assistant container and uses Home Assistant's actual:

- ServiceRegistry and service execution;
- `call_service` event stream;
- StateMachine;
- `state_changed` event stream;
- Context IDs propagated from service calls to service-induced state changes.

A deterministic virtual device supplies only the controlled physical-world delay. Everything being claimed about middleware execution/accounting comes from Home Assistant itself.

## Scientific question

Does a source-recorded ACT2 remain semantically valid after the target Home Assistant state-feedback law changes?

The source device reports state inside the controller deadline. The target device reports state after the deadline. A live controller therefore changes its next operation from ACT2 to VERIFY.

The experiment compares:

- R0 rigid replay;
- R1 timing-feedback-only replay;
- R2 semantic feedback-preserving replay.

The expected decisive workload is 256/256/384 native HA service-call events per 128-task trial, respectively.

## Files

- `PREREGISTRATION.md` — frozen hypotheses, protocol, promotion gates, and forbidden post-hoc changes.
- `home_assistant_ecological.part*.pyfrag` — ordered source fragments concatenated byte-for-byte by CI before execution; the reconstructed source and its SHA-256 are retained in every replica artifact.
- `validate_result.py` — independent post-run oracle; it recomputes native event conservation, support, controls, and certificate from raw artifacts.
- `aggregate_replicas.py` — requires >=2 independently validated runner replicas before replicated promotion.

## Claim boundary

A passing E3c establishes ecological validity at the Home Assistant middleware semantic layer. It does not by itself establish physical-device, radio, Matter-packet, or household deployment validity.
