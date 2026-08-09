import { validateSemanticIdentity } from "./common.js";
import { discoverHtml } from "./carriers/html.js";
import { discoverInlineTest } from "./carriers/inline.js";
import { discoverMcp } from "./carriers/mcp.js";
import { discoverRfc8288 } from "./carriers/rfc8288.js";
/** Discover positively asserted appeal affordances. Never invokes them. */
export function discoverAppeals(input, options) {
    const semantic = validateSemanticIdentity(options.semantic);
    switch (input.carrier) {
        case "rfc8288":
            return discoverRfc8288(input, semantic);
        case "html":
            return discoverHtml(input, semantic);
        case "mcp":
            return discoverMcp(input, semantic);
        case "inline-test":
            return discoverInlineTest(input, semantic);
    }
}
//# sourceMappingURL=discoverAppeals.js.map