import { contextFromAssertedValue, isNonEmptyString, result } from "../common.js";
import type { AppealAffordance, McpInput } from "../types.js";

// Reuses the exact experimental binding already present in this repository.
export const MCP_SEMANTIC_KEY = "example.appeal/semantic";
export const MCP_CONTEXT_KEY = "example.appeal/context";

function metadata(value: unknown): Readonly<Record<string, unknown>> | undefined {
  return typeof value === "object" && value !== null
    ? (value as Readonly<Record<string, unknown>>)
    : undefined;
}

export function discoverMcp(
  input: McpInput,
  semantic: string,
): AppealAffordance[] {
  const nameCounts = new Map<string, number>();
  for (const tool of input.tools) {
    if (isNonEmptyString(tool.name)) {
      nameCounts.set(tool.name, (nameCounts.get(tool.name) ?? 0) + 1);
    }
  }

  const discovered: AppealAffordance[] = [];
  for (const tool of input.tools) {
    const meta = metadata(tool._meta);
    if (
      !isNonEmptyString(tool.name) ||
      nameCounts.get(tool.name) !== 1 ||
      meta?.[MCP_SEMANTIC_KEY] !== semantic
    ) {
      continue;
    }

    const context = contextFromAssertedValue(meta[MCP_CONTEXT_KEY]);
    if (context === undefined) continue;
    discovered.push(
      result(
        semantic,
        "mcp",
        context,
        { kind: "mcp-tool", toolName: tool.name },
        input.source,
      ),
    );
  }

  return discovered;
}
