# Consumer v0 conformance

All rows below correspond to executable cases in `test/` and `fixtures/`; they are not illustrative claims. The injected identity is the clearly non-production `https://appeal.example/rels/appeal` placeholder.

## Core data-driven cases

| Test ID | Carrier | Canonical semantic | Provider known to consumer? | Expected and observed |
|---|---|---:|---:|---|
| `rfc-canonical-multiple` | RFC 8288 | yes | no identity used | EMIT 2, preserve one decision context and order |
| `rfc-supported-anchor` | RFC 8288 | yes | no identity used | EMIT 1 with resolved issue-local anchor context |
| `html-canonical-multiple` | HTML | yes | no identity used | EMIT 2 link handoffs |
| `mcp-same-semantic-two-levels` | MCP | yes | no identity used | EMIT 2 under distinct level-one/level-two contexts |
| `inline-multiple-occurrences` | inline test | yes | no identity used | EMIT 2 occurrence handoffs; no priority assertion |
| `title-appeal-without-semantic` | RFC 8288 | no | no identity used | OMIT |
| `description-appeal-without-semantic` | inline test | no | no identity used | OMIT |
| `rel-help` | RFC 8288 | no | no identity used | OMIT |
| `provider-local-rel-appeal` | RFC 8288 | no global identity | no identity used | OMIT |
| `mcp-name-only` | MCP | no | no identity used | OMIT |
| `mcp-description-only` | MCP | no | no identity used | OMIT |
| `inline-label-only` | inline test | no | no identity used | OMIT |
| `initial-review-human-text` | HTML | no | no identity used | OMIT |
| `wrong-canonical-semantic` | MCP | wrong identity | no identity used | OMIT |
| `mcp-semantic-without-context` | MCP | yes | no identity used | OMIT because applicability context is missing |
| `ambiguous-duplicate-anchor` | RFC 8288 | yes | no identity used | OMIT because context cannot be applied unambiguously |
| `empty-open-world-result` | MCP | absent | no identity used | Return exactly `[]`, not a negative eligibility assertion |

Observed core fixture totals:

```text
positive fixture cases: 5
positive affordance occurrences: 9
negative fixture cases: 12
```

## Central unknown-provider case

| Test ID | Carrier | Local name | Canonical semantic | Provider known? | Expected and observed |
|---|---|---|---:|---:|---|
| `central bootstrap: unknown provider, opaque tool, zero mapping` | MCP | `x92` | yes | no | EMIT 1 |

`fixtures/unknown-provider-mcp.json` is loaded after the consumer module. Its `provider` field stays outside `discoverAppeals`; only its carrier input is passed. The generic source contains neither the provider identity nor a branch that could recognize it.

Combined positive total including this central case: 6 fixture cases and 10 emitted affordance occurrences.

## Vocabulary mutation cases

| Fixture pair | Changed local vocabulary | Canonical semantic changed? | Observed |
|---|---|---:|---|
| `rfc-title-mutation` | `appeal` → `x91` | no | EMIT before and after |
| `html-visible-label-mutation` | `requestReview` → `wf_7` | no | EMIT before and after |
| `mcp-tool-vocabulary-mutation` | `challenge_enforcement` → `a02`; description made opaque | no | EMIT before and after; handoff reflects the new carrier-native tool name |
| `inline-label-mutation` | `seek_redetermination` → `zz19` | no | EMIT before and after |

These four pairs make eight positive discovery calls. They demonstrate stable semantic routing, not stable execution references: where a carrier-native tool name changes, the returned safe handoff changes with it.

## Architecture and boundary assertions

Executable tests also verify:

- provider-specific semantic mappings in generic source: **0**;
- provider-specific semantic branches in generic source: **0**;
- carrier adapters: **4**;
- LLM/classifier/synonym runtime calls: **0**;
- third-party provenance is retained only as `source.locator`, not promoted to trust or officiality;
- actor, standing, eligibility, authorization, deadlines, freshness, and remaining-attempt fields are absent; and
- an injected bare `appeal` identity is rejected because v0 requires an absolute extension URI.

## Execution boundary by carrier

| Carrier | Result boundary | Not demonstrated |
|---|---|---|
| RFC 8288 | Link target handoff | HTTP method, form, authorization, successful invocation |
| HTML | Link target handoff | UI meaning, form execution, document authority, successful invocation |
| MCP | Inline tool-name handoff | Tool safety, eligibility, schema satisfaction, invocation |
| Inline test | Inline occurrence-ID handoff | Public schema, action ontology, execution protocol |

Security invariant:

```text
discovery != authorization
semantic != trust
snapshot != invocation guarantee
```
