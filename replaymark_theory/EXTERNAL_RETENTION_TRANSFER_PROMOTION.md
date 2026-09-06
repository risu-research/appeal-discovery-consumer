# ReplayMark External Retention-Transfer — Promotion Record

**Decision:** `PROMOTED_SOURCE_TRANSFER`  
**Promotion scope:** source-level external claim-boundary transfer only  
**External INVALID:** **not promoted**  
**External downstream flip:** **not promoted**

## Authority chain

- Theory base: `replaymark-theory-sufficiency@5a75e3b99d7602d3506555fda12192d8903a7eb8`
- External-transfer branch: `replaymark-external-retention-transfer-final`
- Protocol freeze commit: `c7e60c5e03712e7a30ac1e53bccfa2025bfb6fa1`
- Auditor commit: `920b759c660a711d94f7aa92bd8059acba8965dc`
- Decisive workflow head: `96edce97f4b79641dcf4b1975e18218f39e37c97`
- GitHub Actions run: `34014534101`
- Workflow conclusion: `success`
- Promoted artifact ID: `9983484671`
- Artifact name: `replaymark-external-retention-transfer`
- Artifact ZIP digest: `sha256:44a5adf0ee21f5b4397ab0c1633bea1aeb195787058986a53b6488c3695a7969`
- Decisive artifact `EXTERNAL_RETENTION_TRANSFER_RESULTS.json` SHA-256: `9d50b293722620e1dcb7ab7bf28983227fc7c344e41e99549fc4a6ffd19e307a`
- Decisive artifact `EXTERNAL_RETENTION_TRANSFER_REPORT.md` SHA-256: `999601e3221f1f03030268a8338a2cc5c20a0b873e31fc6746f4183163243c3a`

The protocol was committed before the decisive workflow execution. The workflow fetched public third-party files by immutable upstream commit and verified their exact Git blob identities before adjudication.

## External pins

### NVIDIA TensorRT-LLM

Commit: `26092ade9de608a71695bfc5800c956b8658ee98`

- replay engine blob `8561acd566853d9582093aa67af3c468ff87d3da`
- shipped trace blob `b072d91ba795936957c1d6318f0b0c5e82ea9901`
- trace-replay README blob `fcf57ede2452aeee8294fa8990c0976ed3509061`
- official technical-blog source blob `9b6a6321f24fb777994c032f9fd96458ea366329`

### AIPerf / AgentX

Commit: `13ae4f6b6b5363007ad52ee2470c3b49c9403b34`

- Weka tutorial blob `8e84b82264750e729ca41a9cdab6c3e237fc6eed`
- AgentX MVP tutorial blob `2a8210ecd31f95c699e53c43f104b620a7c18c80`
- Weka loader source blob `6aa56f42fe83fa443263f0abc6dff0aa6732e245`

## Decisive gates

| Gate | Result |
|---|---|
| G0 exact upstream integrity | PASS |
| G1 NVIDIA source transfer | PASS |
| G2 AIPerf independent source transfer | PASS |
| G3 external retention-transfer promotion | PASS |
| G4 external target-native INVALID | NOT SATISFIED |
| G5 external downstream conclusion flip | NOT SATISFIED |

## NVIDIA result

The pinned shipped trace has **70 events**. Exactly **23 assistant events carry non-empty historical `tool_calls`** and there are **23 historical `tool_call` events**. The first mechanical witness is:

- assistant event index 2: historical `tool_calls=["read_file"]`
- following tool event index 3: `tool_name="read_file"`

The pinned replay implementation simultaneously satisfies the frozen invariants:

1. assistant replay invokes a fresh generation through `self.worker.run_task`;
2. the historical tool event is handled separately from recorded `duration_ms` by `asyncio.sleep`;
3. the fresh assistant-generation path does not consult `event.tool_calls` to certify that the target output selected the historical tool;
4. `ReplayEngine.launch_trace` iterates the recorded `trace.events` and queues the later historical events.

Therefore ReplayMark distinguishes two claims:

- `C_fixed`: **`LICENSED_AS_FIXED_WORKLOAD_OBJECT`** with respect to the retention question. The benchmark may intentionally define the historical structure as exogenous serving workload.
- `C_native`: **`UNRESOLVED`** from this replay artifact alone. The evidence does not certify that a live agent using the fresh target model would choose the retained historical tool/path.

No `INVALID` verdict is inferred because absence of a semantic guard is not structural evidence that the target excludes the historical action.

## AIPerf / AgentX independent transfer

The independently authored AIPerf artifact states and implements the complementary source pattern:

- the model actually served may differ from the model names recorded in the trace;
- recorded Weka subagent structure is reconstructed into root/child conversations with `SPAWN` / `SPAWN_JOIN` dependencies.

ReplayMark again gives the claim-sensitive boundary:

- fixed historical traffic/serving claim: **`LICENSED_AS_FIXED_WORKLOAD_OBJECT`** with respect to retention;
- claim that the newly configured target model's live agent would itself choose the same recorded subagent topology: **`UNRESOLVED`** without target-decision evidence.

## Licensed scientific claim

> Two independently authored, current agent-serving trace-replay implementations retain historical agent structure while permitting a different or fresh serving target. ReplayMark does not reject their fixed-workload serving claims; it identifies that the same replay evidence alone does not license the stronger claim that the target model's live agent would generate the retained path.

This is a real external transfer of ReplayMark's **claim-relative retention boundary** and of its `UNRESOLVED` epistemic outcome. It is stronger than a literature analogy because the result was mechanically checked against pinned third-party implementation artifacts and a shipped trace.

## Claims explicitly not licensed

Do **not** state that:

- TensorRT-LLM trace replay is globally invalid;
- AgentX is globally invalid;
- either fresh target definitely chooses a different tool or branch;
- source audit establishes `INVALID`;
- source audit establishes an external performance/capacity/ranking flip.

Those require G4/G5 evidence not present here.

## Next-gate decision

G3 is scientifically complete. G4 should be attempted only if a natural, reproducible target-native comparator can preserve the external task semantics. A mock target or reconstructed private/missing trace content is not sufficient for promotion. If such a comparator cannot be obtained cleanly, freeze this result and use it as external claim-boundary validation rather than diluting it with an artificial `INVALID` example.
