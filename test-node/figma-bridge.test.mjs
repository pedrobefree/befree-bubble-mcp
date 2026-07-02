import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { createFigmaBridgeServer } from "../bridge/figma/server.mjs";

async function withBridge(options, callback) {
  const server = createFigmaBridgeServer(options);

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    const baseUrl = `http://127.0.0.1:${address.port}`;
    await callback(baseUrl);
  } finally {
    await new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  }
}

async function jsonRequest(baseUrl, route, options = {}) {
  const response = await fetch(`${baseUrl}${route}`, {
    ...options,
    headers: {
      ...(options.body ? { "content-type": "application/json" } : {}),
      ...options.headers,
    },
  });

  const body = await response.json();
  return { response, body };
}

test("GET /health returns ok", async () => {
  await withBridge({}, async (baseUrl) => {
    const { response, body } = await jsonRequest(baseUrl, "/health");

    assert.equal(response.status, 200);
    assert.equal(response.headers.get("access-control-allow-origin"), "*");
    assert.deepEqual(body, { ok: true, service: "figma-bridge" });
  });
});

test("OPTIONS preflight allows Figma UI fetches", async () => {
  await withBridge({}, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/profiles`, {
      method: "OPTIONS",
      headers: {
        origin: "https://www.figma.com",
        "access-control-request-method": "GET",
      },
    });

    assert.equal(response.status, 204);
    assert.equal(response.headers.get("access-control-allow-origin"), "*");
    assert.match(response.headers.get("access-control-allow-methods") || "", /GET/);
  });
});

test("GET /profiles reads settings.json profiles when available", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "figma-bridge-"));
  const configDir = path.join(root, "config");
  await mkdir(configDir);
  await writeFile(
    path.join(configDir, "settings.json"),
    JSON.stringify({
      default_profile: "smoke",
      profiles: {
        smoke: { app_id: "bovichain-g3", appname: "bovichain-g3" },
      },
    }),
    "utf8",
  );

  await withBridge({ configDir }, async (baseUrl) => {
    const { response, body } = await jsonRequest(baseUrl, "/profiles");

    assert.equal(response.status, 200);
    assert.deepEqual(body, {
      ok: true,
      profiles: ["smoke"],
      default: "smoke",
      profile_details: {
        smoke: { app_id: "bovichain-g3", appname: "bovichain-g3" },
      },
    });
  });
});

test("GET /profiles returns an empty list when settings.json is missing", async () => {
  const configDir = await mkdtemp(path.join(tmpdir(), "figma-bridge-empty-"));

  await withBridge({ configDir }, async (baseUrl) => {
    const { response, body } = await jsonRequest(baseUrl, "/profiles");

    assert.equal(response.status, 200);
    assert.deepEqual(body, { ok: true, profiles: [], default: "", profile_details: {} });
  });
});

test("POST /sync saves JSON payload without auth when no token is configured", async () => {
  const dataDir = await mkdtemp(path.join(tmpdir(), "figma-bridge-data-"));
  const payload = { fileKey: "abc123", nodes: [{ id: "1:2" }] };

  await withBridge({ dataDir, token: "" }, async (baseUrl) => {
    const { response, body } = await jsonRequest(baseUrl, "/sync", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    assert.equal(response.status, 200);
    assert.equal(body.ok, true);

    const files = await readdir(dataDir);
    assert.equal(files.length, 1);
    assert.deepEqual(JSON.parse(await readFile(path.join(dataDir, files[0]), "utf8")), payload);
  });
});

test("POST /sync requires bearer auth when token is configured", async () => {
  const dataDir = await mkdtemp(path.join(tmpdir(), "figma-bridge-auth-"));

  await withBridge({ dataDir, token: "secret-token" }, async (baseUrl) => {
    const unauthorized = await jsonRequest(baseUrl, "/sync", {
      method: "POST",
      body: JSON.stringify({ ok: true }),
    });

    assert.equal(unauthorized.response.status, 401);
    assert.deepEqual(unauthorized.body, { ok: false, error: "unauthorized" });

    const authorized = await jsonRequest(baseUrl, "/sync", {
      method: "POST",
      headers: { authorization: "Bearer secret-token" },
      body: JSON.stringify({ ok: true }),
    });

    assert.equal(authorized.response.status, 200);
    assert.equal(authorized.body.ok, true);
  });
});
