import { createServer } from "node:http";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const DEFAULT_HOST = "0.0.0.0";
const DEFAULT_PORT = 3333;
const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(MODULE_DIR, "..", "..");

function sendJson(res, statusCode, body) {
  const payload = JSON.stringify(body);
  res.writeHead(statusCode, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(payload),
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "authorization,content-type",
  });
  res.end(payload);
}

function sendCorsPreflight(res) {
  res.writeHead(204, {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "authorization,content-type",
    "access-control-max-age": "86400",
  });
  res.end();
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
    return { names: [], defaultProfile: "", details: {} };
  }

  try {
    const settingsPath = path.join(configDir, "settings.json");
    const settings = JSON.parse(await readFile(settingsPath, "utf8"));
    const profiles = settings?.profiles;

    if (Array.isArray(profiles)) {
      const names = profiles
        .map((profile) => profile?.name ?? profile?.id ?? profile?.app_id ?? profile?.appname)
        .filter(Boolean)
        .map(String);
      return {
        names,
        defaultProfile: String(settings?.default_profile || names[0] || ""),
        details: profiles,
      };
    }

    if (profiles && typeof profiles === "object") {
      const names = Object.keys(profiles);
      return {
        names,
        defaultProfile: String(settings?.default_profile || names[0] || ""),
        details: profiles,
      };
    }

    return { names: [], defaultProfile: "", details: {} };
  } catch (error) {
    if (error?.code === "ENOENT") {
      return { names: [], defaultProfile: "", details: {} };
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
  return filePath;
}

async function pathExists(candidate) {
  try {
    await access(candidate);
    return true;
  } catch {
    return false;
  }
}

async function resolvePython() {
  if (process.env.BUBBLE_MCP_PYTHON) {
    return process.env.BUBBLE_MCP_PYTHON;
  }
  if (process.env.VIRTUAL_ENV) {
    const virtualEnvPython = path.join(process.env.VIRTUAL_ENV, "bin", "python");
    if (await pathExists(virtualEnvPython)) {
      return virtualEnvPython;
    }
  }
  const repoPython = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (await pathExists(repoPython)) {
    return repoPython;
  }
  return "python3";
}

function extractProcessError(stdout, stderr, code) {
  const lines = `${stderr}\n${stdout}`
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const tracebackIndex = lines.findLastIndex((line) => line.includes("Traceback"));
  if (tracebackIndex >= 0) {
    return lines.slice(Math.max(tracebackIndex, lines.length - 4)).join(": ");
  }
  return lines.at(-1) || `figma bridge sync exited with code ${code}`;
}

async function triggerStandaloneSync(filePath) {
  const python = await resolvePython();
  const args = ["-m", "bubble_mcp.figma_bridge", "--file", filePath];
  const sourcePath = path.join(REPO_ROOT, "src");
  const pythonPath = process.env.PYTHONPATH
    ? `${sourcePath}${path.delimiter}${process.env.PYTHONPATH}`
    : sourcePath;
  console.log(`[Bridge] → Auto-triggering sync: ${python} ${args.join(" ")}`);

  return await new Promise((resolve, reject) => {
    const child = spawn(python, args, {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONPATH: pythonPath },
    });
    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      stdout += text;
      process.stdout.write(`[sync] ${text}`);
    });
    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      process.stderr.write(`[sync:err] ${text}`);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        try {
          resolve(JSON.parse(stdout));
        } catch {
          resolve({ ok: true, stdout });
        }
        return;
      }
      const error = new Error(extractProcessError(stdout, stderr, code));
      error.code = code;
      error.stdout = stdout;
      error.stderr = stderr;
      reject(error);
    });
  });
}

export function createFigmaBridgeServer(options = {}) {
  const configDir = options.configDir ?? process.env.BUBBLE_MCP_CONFIG_DIR;
  const dataDir = options.dataDir ?? path.join(process.cwd(), "tmp", "bridge_data");
  const token = options.token ?? process.env.BUBBLE_MCP_BRIDGE_TOKEN;
  const syncHandler = options.syncHandler ?? triggerStandaloneSync;

  return createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");

    try {
      if (req.method === "OPTIONS") {
        sendCorsPreflight(res);
        return;
      }

      if (req.method === "GET" && url.pathname === "/health") {
        sendJson(res, 200, { ok: true, service: "figma-bridge" });
        return;
      }

      if (req.method === "GET" && url.pathname === "/profiles") {
        const profiles = await readProfiles(configDir);
        sendJson(res, 200, {
          ok: true,
          profiles: profiles.names,
          default: profiles.defaultProfile,
          profile_details: profiles.details,
        });
        return;
      }

      if (req.method === "POST" && url.pathname === "/sync") {
        if (!hasValidBearerToken(req, token)) {
          sendJson(res, 401, { ok: false, error: "unauthorized" });
          return;
        }

        const payload = await readRequestJson(req);
        const filePath = await saveSyncPayload(dataDir, payload);
        const result = await syncHandler(filePath, payload);
        sendJson(res, 200, { ok: true, saved_as: path.basename(filePath), result });
        return;
      }

      sendJson(res, 404, { ok: false, error: "not_found" });
    } catch (error) {
      sendJson(res, 500, {
        ok: false,
        error: error instanceof SyntaxError ? "invalid_json" : "internal_error",
        message: error instanceof Error ? error.message : String(error),
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
