import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { discoverAppeals } from "../dist/index.js";

const fixture = JSON.parse(
  await readFile(new URL("../fixtures/vocabulary-mutations.json", import.meta.url), "utf8"),
);

for (const pair of fixture.pairs) {
  test(`vocabulary mutation: ${pair.id}`, () => {
    const before = discoverAppeals(pair.before, { semantic: fixture.semantic });
    const after = discoverAppeals(pair.after, { semantic: fixture.semantic });
    assert.equal(before.length, 1);
    assert.equal(after.length, 1);
    assert.equal(before[0].semantic, after[0].semantic);
    assert.equal(before[0].carrier, after[0].carrier);
    assert.deepEqual(before[0].context, after[0].context);
    assert.equal(before[0].affordance.kind, after[0].affordance.kind);
    if (pair.id === "mcp-tool-vocabulary-mutation") {
      assert.equal(before[0].affordance.toolName, "challenge_enforcement");
      assert.equal(after[0].affordance.toolName, "a02");
    } else {
      assert.deepEqual(before[0].affordance, after[0].affordance);
    }
  });
}
