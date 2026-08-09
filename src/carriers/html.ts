import { parse } from "parse5";

import { result } from "../common.js";
import type { AppealAffordance, HtmlInput } from "../types.js";

type HtmlAttribute = Readonly<{ name: string; value: string }>;
type HtmlNode = Readonly<{
  nodeName?: string;
  attrs?: readonly HtmlAttribute[];
  childNodes?: readonly HtmlNode[];
}>;

const LINK_ELEMENTS = new Set(["a", "area", "link"]);

function attribute(node: HtmlNode, name: string): string | undefined {
  return node.attrs?.find((item) => item.name === name)?.value;
}

function walk(node: HtmlNode, visit: (node: HtmlNode) => void): void {
  visit(node);
  for (const child of node.childNodes ?? []) walk(child, visit);
}

function absolute(reference: string, base: string): string | undefined {
  try {
    return new URL(reference, base).href;
  } catch {
    return undefined;
  }
}

/** Uses a real HTML parser; only a/area/link rel tokens and href are recognized. */
export function discoverHtml(
  input: HtmlInput,
  semantic: string,
): AppealAffordance[] {
  const documentUrl = absolute(input.documentUrl, input.documentUrl);
  if (documentUrl === undefined) return [];

  const document = parse(input.html) as unknown as HtmlNode;
  let firstBaseHref: string | undefined;
  walk(document, (node) => {
    if (firstBaseHref === undefined && node.nodeName === "base") {
      firstBaseHref = attribute(node, "href");
    }
  });

  const baseUrl =
    firstBaseHref === undefined ? documentUrl : absolute(firstBaseHref, documentUrl);
  if (baseUrl === undefined) return [];

  const discovered: AppealAffordance[] = [];
  walk(document, (node) => {
    if (!LINK_ELEMENTS.has(node.nodeName ?? "")) return;
    const relation = attribute(node, "rel");
    const href = attribute(node, "href");
    if (relation === undefined || href === undefined) return;

    const relations = relation.split(/[\t\n\f\r ]+/u).filter(Boolean);
    if (!relations.includes(semantic)) return;
    const target = absolute(href, baseUrl);
    if (target === undefined) return;

    discovered.push(
      result(
        semantic,
        "html",
        { kind: "uri", value: documentUrl },
        { kind: "link", target },
        input.source,
      ),
    );
  });

  return discovered;
}
