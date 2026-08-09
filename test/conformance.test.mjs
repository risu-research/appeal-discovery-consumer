import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { discoverAppeals } from "../dist/index.js";

const fixture = JSON.parse(
  await readFile(new URL("../fixtures/conformance.json", import.meta.url), "utf8"),
);

function handoffReference(result) {
  switch (result.affordance.kind) {
    case "link":
      return result.affordance.target;
    case "mcp-tool":
      return result.affordance.toolName;
    case "inline-action":
      return result.affordance.actionId;
  }
}

for (const conformanceCase of fixture.cases) {
  test(`conformance: ${conformanceCase.id}`, () => {
    const results = discoverAppeals(conformanceCase.input, {
      semantic: fixture.semantic,
    });

    assert.equal(results.length, conformanceCase.expected.count);
    assert.deepEqual(
      results.map((item) => item.context.value),
      conformanceCase.expected.contexts,
    );
    assert.deepEqual(
      results.map(handoffReference),
      conformanceCase.expected.handoffs,
    );
    assert.ok(results.every((item) => item.semantic === fixture.semantic));

    if (conformanceCase.id === "empty-open-world-result") {
      assert.deepEqual(results, []);
    }
  });
}

test("configured semantic identity must be an absolute URI", () => {
  assert.throws(
    () => discoverAppeals({ carrier: "mcp", tools: [] }, { semantic: "appeal" }),
    /absolute URI/u,
  );
});

test("RFC 8288 extension relation URIs compare case-insensitively character by character", () => {
  const results = discoverAppeals(
    {
      carrier: "rfc8288",
      representationUrl: "https://rfc.test/decisions/case-folding",
      linkHeaders: [
        "</appeals/case-folding>; rel=\"HTTPS://APPEAL.EXAMPLE/RELS/APPEAL\"",
      ],
    },
    { semantic: fixture.semantic },
  );

  assert.equal(results.length, 1);
  assert.equal(results[0].semantic, fixture.semantic);
  assert.equal(results[0].affordance.kind, "link");
  assert.equal(
    results[0].affordance.target,
    "https://rfc.test/appeals/case-folding",
  );
});
