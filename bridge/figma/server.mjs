import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 47831;

function sendJson(res, statusCode, body) {
  const payload = JSON.stringify(body);
  res.writeHead(statusCode, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

function readRequestJson(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];

    req.on("data", (chunk) => {
      chunks.push(chunk);
    });

    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");

      if (!raw.trim()) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(error);
      }
    });

    req.on("error", reject);
  });
}

async function readProfiles(configDir) {
  if (!configDir) {
    return [];
  }

  try {
    const settingsPath = path.join(configDir, "settings.json");
    const settings = JSON.parse(await readFile(settingsPath, "utf8"));
    const profiles = settings?.profiles;

    if (Array.isArray(profiles)) {
      return profiles;
    }

    if (profiles && typeof profiles === "object") {
      return profiles;
    }

    return [];
  } catch (error) {
    if (error?.code === "ENOENT") {
      return [];
    }

    throw error;
  }
}

function hasValidBearerToken(req, token) {
  if (!token) {
    return true;
  }

  return req.headers.authorization === `Bearer ${token}`;
}

async function saveSyncPayload(dataDir, payload) {
  await mkdir(dataDir, { recursive: true });
  const fileName = `${Date.now()}-${randomUUID()}.json`;
  const filePath = path.join(dataDir, fileName);
  await writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

export function createFigmaBridgeServer(options = {}) {
  const configDir = options.configDir ?? process.env.BUBBLE_MCP_CONFIG_DIR;
  const dataDir = options.dataDir ?? path.join(process.cwd(), "tmp", "bridge_data");
  const token = options.token ?? process.env.BUBBLE_MCP_BRIDGE_TOKEN;

  return createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");

    try {
      if (req.method === "GET" && url.pathname === "/health") {
        sendJson(res, 200, { ok: true });
        return;
      }

      if (req.method === "GET" && url.pathname === "/profiles") {
        sendJson(res, 200, { profiles: await readProfiles(configDir) });
        return;
      }

      if (req.method === "POST" && url.pathname === "/sync") {
        if (!hasValidBearerToken(req, token)) {
          sendJson(res, 401, { ok: false, error: "unauthorized" });
          return;
        }

        const payload = await readRequestJson(req);
        await saveSyncPayload(dataDir, payload);
        sendJson(res, 200, { ok: true });
        return;
      }

      sendJson(res, 404, { ok: false, error: "not_found" });
    } catch (error) {
      sendJson(res, 500, {
        ok: false,
        error: error instanceof SyntaxError ? "invalid_json" : "internal_error",
      });
    }
  });
}

function isDirectRun() {
  if (!process.argv[1]) {
    return false;
  }

  return import.meta.url === pathToFileURL(process.argv[1]).href;
}

if (isDirectRun()) {
  const host = process.env.BUBBLE_MCP_BRIDGE_HOST || DEFAULT_HOST;
  const port = Number.parseInt(process.env.BUBBLE_MCP_BRIDGE_PORT || `${DEFAULT_PORT}`, 10);
  const server = createFigmaBridgeServer();

  server.listen(port, host, () => {
    const address = server.address();
    const actualPort = typeof address === "object" && address ? address.port : port;
    console.log(`Figma bridge listening on http://${host}:${actualPort}`);
  });
}
