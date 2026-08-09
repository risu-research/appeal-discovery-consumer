import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { discoverAppeals } from "../dist/index.js";

const root = fileURLToPath(new URL("..", import.meta.url));
const fixture = JSON.parse(
  await readFile(new URL("../fixtures/unknown-provider-mcp.json", import.meta.url), "utf8"),
);

test("central bootstrap: unknown provider, opaque tool, zero mapping", () => {
  // Deliberately pass only carrier data. Provider identity remains outside the API.
  const results = discoverAppeals(fixture.input, { semantic: fixture.semantic });
  assert.equal(results.length, 1);
  assert.deepEqual(results[0], {
    semantic: fixture.semantic,
    carrier: "mcp",
    context: { kind: "uri", value: fixture.expected.context },
    affordance: { kind: "mcp-tool", toolName: fixture.expected.toolName },
    source: { locator: fixture.expected.sourceLocator },
  });
});

test("source metadata is provenance only and is narrowed on output", () => {
  const [result] = discoverAppeals(fixture.input, { semantic: fixture.semantic });
  assert.deepEqual(Object.keys(result.source), ["locator"]);
  assert.equal("trusted" in result.source, false);
  assert.equal("official" in result.source, false);
});

test("outputs synthesize no actor or temporal assertions", () => {
  const [result] = discoverAppeals(fixture.input, { semantic: fixture.semantic });
  const forbidden = [
    "actor",
    "standing",
    "eligible",
    "eligibleParty",
    "validUntil",
    "expiresAt",
    "appealDeadline",
    "remainingAppeals",
    "trusted",
    "official",
    "authorized",
  ];
  const serialized = JSON.stringify(result);
  for (const field of forbidden) {
    assert.doesNotMatch(serialized, new RegExp(`\"${field}\"`, "u"));
  }
});

test("static guard: discovery source has no known provider coupling or inference client", async () => {
  const sourceDirectory = path.join(root, "src");
  const carrierDirectory = path.join(sourceDirectory, "carriers");
  const sourceFiles = [
    path.join(sourceDirectory, "common.ts"),
    path.join(sourceDirectory, "discoverAppeals.ts"),
    path.join(sourceDirectory, "types.ts"),
    ...(await readdir(carrierDirectory)).map((name) => path.join(carrierDirectory, name)),
  ];
  const source = (await Promise.all(sourceFiles.map((name) => readFile(name, "utf8")))).join("\n");

  assert.doesNotMatch(source.toLowerCase(), /provider/u);

  for (const providerName of [
    "paypal",
    "google",
    "ebay",
    "oracle",
    "microsoft",
    "cloudflare",
    "unknown-provider-7",
  ]) {
    assert.doesNotMatch(source.toLowerCase(), new RegExp(providerName, "u"));
  }
  for (const inferenceMarker of ["openai", "anthropic", "classifier", "synonym"]) {
    assert.doesNotMatch(source.toLowerCase(), new RegExp(inferenceMarker, "u"));
  }

  const carrierSource = (
    await Promise.all(
      (await readdir(carrierDirectory)).map((name) =>
        readFile(path.join(carrierDirectory, name), "utf8"),
      ),
    )
  ).join("\n");
  for (const forbiddenInferenceInput of [
    ".description",
    ".label",
    "textcontent",
    "aria-label",
    "classname",
  ]) {
    assert.doesNotMatch(
      carrierSource.toLowerCase(),
      new RegExp(forbiddenInferenceInput.replace(".", "\\."), "u"),
    );
  }
});
