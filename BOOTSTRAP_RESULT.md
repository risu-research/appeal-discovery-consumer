VERDICT: PASS

## 1. What exactly was demonstrated?

A generic consumer deterministically discovered appeal affordance occurrences from RFC 8288 Link metadata, HTML relations, the repository's existing experimental MCP `_meta` binding, and a deliberately tiny normalized inline test carrier. Matching used exact equality against an injected absolute semantic URI. Results preserved carrier-provided context, cardinality, ordering, source locator, and a safe link/tool/action handoff.

The strongest permitted claim is supported:

> A generic consumer can deterministically recognize an appeal affordance from a previously unknown provider without a provider-specific purpose mapping when that provider emits the shared semantic through an already-supported carrier.

## 2. What was not demonstrated?

No real independent publisher emitted the identity. The fixture does not prove adoption, publisher incentive, stable-URI governance, IANA readiness, legal compliance, target authority, actor eligibility, current invocation success, trust, safe execution, or interoperability of forms/workflows. HTML support is document-context only; it does not infer per-card context on a page containing multiple decisions, and the placeholder is not registered through HTML's extension-link procedure. The RFC 8288 adapter is an explicit safe subset, not a claim of full parser conformance. The inline carrier is not a public schema proposal.

## 3. Did unknown-provider zero-mapping discovery work?

**Yes.** The external `unknown-provider-7` fixture contained an opaque MCP tool named `x92`, no useful description, the existing canonical `_meta` semantic key/value, and an asserted decision context. Provider identity was not passed to the API and does not occur in consumer source. The already-built consumer returned the tool handoff with zero source changes, zero provider mappings, and zero inference calls.

## 4. How many provider-specific semantic branches remain in the generic consumer?

**0.** A static architecture test scans production discovery source for all known corpus provider names and the unknown fixture identity. It also checks for common LLM/classifier markers. The only dispatch branches are the four permitted carrier kinds.

```text
provider-specific semantic mappings: 0
provider-specific semantic branches: 0
carrier-specific adapters: 4
LLM/runtime inference calls: 0
```

## 5. Which carriers are supported?

| Carrier adapter | Discovery handoff |
|---|---|
| RFC 8288 safe subset | Link target |
| HTML explicit relation | Link target |
| Existing experimental MCP `_meta` | Tool name |
| Experimental normalized inline test carrier | Action occurrence ID |

The last carrier is explicitly non-normative and does not grow into an action framework.

## 6. What is the strongest remaining distribution risk?

The test proves only consumer-side technical readiness after a publisher emits the shared assertion. It does not prove that any independent publisher will annotate a native affordance with the same controlled identity. The current URI is reserved example space and cannot bootstrap public reuse. Distribution therefore remains the dominant unresolved layer.

## 7. What is the next smallest external experiment?

Have one genuinely independent server or publisher add one native annotation using a controlled experimental semantic URI through **one already-supported carrier**. Freeze this package and its source before that annotation is produced; inject the agreed URI as configuration, then run the unchanged consumer against the native representation. Record whether context had to be guessed, whether any provider mapping was requested, and whether the publisher found the annotation cost acceptable.

Do not add another carrier or semantic first. That single native-use test has the highest information value because it directly tests the remaining distribution assumption.

## Verification snapshot

```text
pnpm run verify
TypeScript strict typecheck: PASS
Package build: PASS
Node tests: 26 passed, 0 failed

existing Python experiment
7 passed, 0 failed
```

Fixture accounting:

```text
positive fixture cases: 6 (10 emitted occurrences, including unknown provider)
negative fixture cases: 12
vocabulary-mutation fixture pairs: 4 (8 positive calls)
unknown-provider fixtures: 1
```

The security boundary remains:

```text
discovery != authorization
semantic != trust
snapshot != invocation guarantee
```
