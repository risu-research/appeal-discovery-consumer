import { contextFromAssertedValue, isNonEmptyString, result } from "../common.js";
// Reuses the exact experimental binding already present in this repository.
export const MCP_SEMANTIC_KEY = "example.appeal/semantic";
export const MCP_CONTEXT_KEY = "example.appeal/context";
function metadata(value) {
    return typeof value === "object" && value !== null
        ? value
        : undefined;
}
export function discoverMcp(input, semantic) {
    const nameCounts = new Map();
    for (const tool of input.tools) {
        if (isNonEmptyString(tool.name)) {
            nameCounts.set(tool.name, (nameCounts.get(tool.name) ?? 0) + 1);
        }
    }
    const discovered = [];
    for (const tool of input.tools) {
        const meta = metadata(tool._meta);
        if (!isNonEmptyString(tool.name) ||
            nameCounts.get(tool.name) !== 1 ||
            meta?.[MCP_SEMANTIC_KEY] !== semantic) {
            continue;
        }
        const context = contextFromAssertedValue(meta[MCP_CONTEXT_KEY]);
        if (context === undefined)
            continue;
        discovered.push(result(semantic, "mcp", context, { kind: "mcp-tool", toolName: tool.name }, input.source));
    }
    return discovered;
}
//# sourceMappingURL=mcp.js.map