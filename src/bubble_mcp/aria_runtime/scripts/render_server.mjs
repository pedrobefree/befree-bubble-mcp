#!/usr/bin/env node

import http from "node:http";
import { extractRenderedHtml } from "./render_lib.mjs";

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > 5_000_000) {
        reject(new Error("Payload too large"));
        req.destroy();
      }
    });
    req.on("end", () => {
      if (!raw.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (e) {
        reject(new Error(`Invalid JSON: ${e.message}`));
      }
    });
    req.on("error", reject);
  });
}

function sendJson(res, status, data) {
  const payload = JSON.stringify(data);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

const port = Number.parseInt(process.env.PORT || "8787", 10) || 8787;
const defaultTimeout = Number.parseInt(process.env.RENDER_DEFAULT_TIMEOUT_MS || "35000", 10) || 35000;
const maxTimeout = Number.parseInt(process.env.RENDER_MAX_TIMEOUT_MS || "120000", 10) || 120000;

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") {
    sendJson(res, 200, { ok: true, service: "bubble-renderer" });
    return;
  }

  if (req.method === "POST" && req.url === "/render") {
    try {
      const body = await readJsonBody(req);
      const url = String(body.url || "").trim();
      if (!url) {
        sendJson(res, 400, { error: "Missing 'url'" });
        return;
      }
      const selector = String(body.selector || "body").trim() || "body";
      let timeout = Number.parseInt(String(body.timeout_ms || defaultTimeout), 10);
      if (!Number.isFinite(timeout) || timeout <= 0) timeout = defaultTimeout;
      timeout = Math.min(timeout, maxTimeout);

      const result = await extractRenderedHtml({
        url,
        selector,
        timeout,
      });

      sendJson(res, 200, result);
      return;
    } catch (err) {
      sendJson(res, 500, { error: String(err && err.message ? err.message : err) });
      return;
    }
  }

  sendJson(res, 404, { error: "Not found" });
});

server.listen(port, "0.0.0.0", () => {
  process.stdout.write(`Renderer server listening on 0.0.0.0:${port}\n`);
});

