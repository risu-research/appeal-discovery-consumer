import type { AppealAffordance, Rfc8288Input } from "../types.js";
/**
 * Parses a fail-closed RFC 8288 subset: angle-bracket targets, quoted or token
 * parameters, `rel`, and at most one `anchor`. Malformed values are omitted.
 */
export declare function discoverRfc8288(input: Rfc8288Input, semantic: string): AppealAffordance[];
//# sourceMappingURL=rfc8288.d.ts.map