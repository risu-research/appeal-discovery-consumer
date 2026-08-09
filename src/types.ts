export type CarrierKind = "rfc8288" | "html" | "mcp" | "inline-test";

export type ContextRef = Readonly<{
  kind: "uri" | "carrier-local";
  value: string;
}>;

/** Opaque provenance retained for caller policy. It is not a trust assertion. */
export type SourceMetadata = Readonly<{
  locator: string;
}>;

export type LinkHandoff = Readonly<{
  kind: "link";
  target: string;
}>;

export type McpToolHandoff = Readonly<{
  kind: "mcp-tool";
  toolName: string;
}>;

export type InlineActionHandoff = Readonly<{
  kind: "inline-action";
  actionId: string;
}>;

export type AppealAffordance = Readonly<{
  context: ContextRef;
  semantic: string;
  carrier: CarrierKind;
  affordance: LinkHandoff | McpToolHandoff | InlineActionHandoff;
  source?: SourceMetadata;
}>;

export type Rfc8288Input = Readonly<{
  carrier: "rfc8288";
  representationUrl: string;
  linkHeaders: readonly string[];
  source?: SourceMetadata;
}>;

export type HtmlInput = Readonly<{
  carrier: "html";
  documentUrl: string;
  html: string;
  source?: SourceMetadata;
}>;

export type McpTool = Readonly<{
  name?: unknown;
  _meta?: unknown;
  [key: string]: unknown;
}>;

export type McpInput = Readonly<{
  carrier: "mcp";
  tools: readonly McpTool[];
  source?: SourceMetadata;
}>;

export type InlineTestAction = Readonly<{
  id?: unknown;
  semantic?: unknown;
  [key: string]: unknown;
}>;

/**
 * Experimental normalized test carrier. This is not a proposed public action
 * schema and deliberately exposes only an occurrence ID and semantic identity.
 */
export type InlineTestInput = Readonly<{
  carrier: "inline-test";
  context: ContextRef;
  actions: readonly InlineTestAction[];
  source?: SourceMetadata;
}>;

export type DiscoveryInput =
  | Rfc8288Input
  | HtmlInput
  | McpInput
  | InlineTestInput;

export type DiscoveryOptions = Readonly<{
  /** Exact, injected canonical identity. v0 intentionally has no default. */
  semantic: string;
}>;
