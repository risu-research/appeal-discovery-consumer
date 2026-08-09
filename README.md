# Appeal Discovery Consumer v0

Small TypeScript reference consumer for one question:

> Can a previously unknown provider become discoverable without provider-specific semantic mapping when it emits an injected canonical appeal identity through a supported carrier?

The executable answer is **yes, within the four explicitly supported carrier adapters**. See [BOOTSTRAP_RESULT.md](BOOTSTRAP_RESULT.md) for the bounded verdict and [CONFORMANCE.md](CONFORMANCE.md) for the tested cases.

Status: experimental, consumer-first bootstrap artifact. It is not a standard, production semantic URI, publisher-adoption result, or execution library.

## Frozen semantic

Carrier-neutral:

> **Identifies an affordance used to request review or reconsideration of the prior decision identified by or unambiguously associated with its context.**

RFC 8288 binding:

> **Refers to a resource used to request review or reconsideration of the prior decision identified by or unambiguously associated with the link context.**

The implementation recognizes purpose, context, and an affordance occurrence (`S + C + T`). It does not produce actor eligibility (`E`).

## Public API

```ts
import { discoverAppeals } from "appeal-discovery-consumer-v0";

const affordances = discoverAppeals(
  {
    carrier: "mcp",
    tools: toolsFromAnUnfamiliarServer,
  },
  {
    // Reserved example space. Inject a controlled experimental URI in real tests.
    semantic: "https://appeal.example/rels/appeal",
  },
);
```

```ts
discoverAppeals(input, { semantic }) satisfies AppealAffordance[]
```

`semantic` is mandatory and must be an absolute URI. There is deliberately no production default. Matching is exact—no provider table, synonyms, labels, descriptions, regex classification, or LLM.

The result is set-valued and preserves discovery order without assigning priority:

```ts
type AppealAffordance = {
  context: { kind: "uri" | "carrier-local"; value: string };
  semantic: string;
  carrier: "rfc8288" | "html" | "mcp" | "inline-test";
  affordance:
    | { kind: "link"; target: string }
    | { kind: "mcp-tool"; toolName: string }
    | { kind: "inline-action"; actionId: string };
  source?: { locator: string };
};
```

No result means only that no positive assertion was discovered in this input. It does not mean “not appealable,” complete route enumeration, or lack of other remedies.

## Supported carrier adapters

### RFC 8288 / HTTP `Link`

Input is an absolute `representationUrl` plus one or more raw `linkHeaders`. v0 implements a documented, fail-closed subset rather than claiming complete RFC 8288 parsing:

- angle-bracket link targets;
- comma-separated values while respecting quoted strings and angle brackets;
- token or quoted parameters;
- exact matching within the `rel` relation list;
- at most one `anchor`, resolved against the representation URL;
- relative target resolution against the representation URL; and
- multiple matching links in source order.

Malformed values, duplicate `rel`/`anchor` parameters, invalid targets, and anchors that cannot be resolved are omitted. `title` is parsed as ordinary metadata and never supplies purpose. Provider-local `rel="appeal"` does not match the injected extension URI.

This subset follows the context, relation-list, target-resolution, and `anchor` model in [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288.html). It intentionally rejects some inputs that a complete parser could recover by ignoring later duplicate parameters.

### HTML relation binding

HTML is parsed with `parse5`, not regular expressions. Only explicit `rel` tokens on `a`, `area`, and `link` elements are considered. Targets use normal document/first-`base` resolution; context remains the document URL. Text, `title`, CSS, ARIA, surrounding prose, and URL path names are ignored.

This adapter is safe only where the HTML document URL identifies or is unambiguously associated with the relevant prior decision. It does not guess a per-card context from a multi-decision page.

There is a standards caveat: the [HTML Standard's extension procedure](https://html.spec.whatwg.org/multipage/links.html#other-link-types) expects extension link types to be registered in its referenced rel registry. The placeholder URI is not registered there. v0 therefore tests application-level recognition of an explicit parsed `rel` token; it does **not** claim that the placeholder is already a conforming public HTML link type. Exact matching is deliberately narrower than HTML's general case-insensitive keyword processing.

### Existing experimental MCP binding

The consumer reuses the repository's exact non-standard keys:

```text
example.appeal/semantic
example.appeal/context
```

The semantic value must equal the injected URI, context must be asserted, and the MCP tool name must be unique in the input. The result is a tool-name handoff; nothing is invoked. Names and descriptions have no semantic role.

### Inline action occurrence test carrier

`inline-test` is an **experimental normalized test carrier, not a proposed public action schema**. It proves only that an explicitly identified inline occurrence can carry the semantic without a unique URL. It retains an occurrence ID and explicit context; it adds no method, form, policy, eligibility, or workflow model.

## Integrity and security boundary

The consumer never strengthens the source assertion:

```text
discovery != authorization
semantic != trust
snapshot != invocation guarantee
```

- It does not invoke links, tools, or inline actions.
- It returns no `eligible`, actor, standing, deadline, freshness, trust, officiality, or authorization field.
- `source.locator` is opaque provenance for caller policy. Extra `trusted` or `official` input fields are discarded.
- Targets and tool/action references remain untrusted carrier-native handoffs.
- Absence is open-world and returns `[]`.
- Multiple results are neither ranked nor declared equivalent or exhaustive.

## Install and verify

Requirements: Node 20+ and pnpm.

```sh
pnpm install --frozen-lockfile
pnpm run verify
```

`verify` runs strict TypeScript checking, a clean build, and the Node test suite. There is one runtime dependency (`parse5`) and one development dependency (`typescript`). The HTML parser is the only runtime dependency because structural regex extraction would not support the fail-closed claim.

## Deliberate exclusions

No submission API, HTTP client, authentication, crawler, provider adapter, natural-language classifier, trust policy, action ontology, workflow protocol, or universal relation parser is included.
