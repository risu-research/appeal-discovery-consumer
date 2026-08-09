import { parse } from "parse5";
import { result } from "../common.js";
const LINK_ELEMENTS = new Set(["a", "area", "link"]);
function attribute(node, name) {
    return node.attrs?.find((item) => item.name === name)?.value;
}
function walk(node, visit) {
    visit(node);
    for (const child of node.childNodes ?? [])
        walk(child, visit);
}
function absolute(reference, base) {
    try {
        return new URL(reference, base).href;
    }
    catch {
        return undefined;
    }
}
/** Uses a real HTML parser; only a/area/link rel tokens and href are recognized. */
export function discoverHtml(input, semantic) {
    const documentUrl = absolute(input.documentUrl, input.documentUrl);
    if (documentUrl === undefined)
        return [];
    const document = parse(input.html);
    let firstBaseHref;
    walk(document, (node) => {
        if (firstBaseHref === undefined && node.nodeName === "base") {
            firstBaseHref = attribute(node, "href");
        }
    });
    const baseUrl = firstBaseHref === undefined ? documentUrl : absolute(firstBaseHref, documentUrl);
    if (baseUrl === undefined)
        return [];
    const discovered = [];
    walk(document, (node) => {
        if (!LINK_ELEMENTS.has(node.nodeName ?? ""))
            return;
        const relation = attribute(node, "rel");
        const href = attribute(node, "href");
        if (relation === undefined || href === undefined)
            return;
        const relations = relation.split(/[\t\n\f\r ]+/u).filter(Boolean);
        if (!relations.includes(semantic))
            return;
        const target = absolute(href, baseUrl);
        if (target === undefined)
            return;
        discovered.push(result(semantic, "html", { kind: "uri", value: documentUrl }, { kind: "link", target }, input.source));
    });
    return discovered;
}
//# sourceMappingURL=html.js.map