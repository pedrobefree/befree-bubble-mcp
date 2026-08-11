import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readExtensionFile = (name) => readFile(
  new URL(`../chrome-extension/${name}`, import.meta.url),
  "utf8",
);

test("extension bridge restricts page messages to the current origin", async () => {
  const [content, bridge] = await Promise.all([
    readExtensionFile("content.js"),
    readExtensionFile("bridge.js"),
  ]);

  assert.match(content, /postMessage\(\{ type, payload \}, window\.location\.origin\)/);
  assert.doesNotMatch(content, /postMessage\([^\n]+, ['"]\*['"]\)/);
  assert.match(bridge, /event\.origin !== window\.location\.origin/);
});

test("extension popup renders captured metadata as text", async () => {
  const popup = await readExtensionFile("popup.js");

  assert.doesNotMatch(popup, /eventsList\.innerHTML/);
  assert.match(popup, /metaNode\.textContent/);
  assert.match(popup, /eventsList\.replaceChildren/);
});
