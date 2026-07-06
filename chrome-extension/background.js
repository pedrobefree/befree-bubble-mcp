/**
 * Befree Bubble MCP Companion — Background Service Worker
 *
 * Local-only bridge for Bubble editor captures. No account, email/password,
 * access token, refresh token, or remote relay is used here.
 */

'use strict';

const DEFAULT_PORT = 3847;
const PORT_SCAN_RANGE = 10;
const DEFAULT_ENABLED = true;
const DEFAULT_CAPTURE_KEY = '';
const STORAGE_KEYS = {
  enabled: 'mcpEnabled',
  port: 'mcpPort',
  captureKey: 'mcpCaptureKey',
  eventLog: 'mcpEventLog',
};
const MAX_EVENTS = 50;

let stats = { captured: 0, sent: 0, errors: 0, writes: 0, structure: 0 };

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function storageSet(data) {
  return new Promise((resolve) => chrome.storage.local.set(data, resolve));
}

async function getEnabled() {
  const data = await storageGet({ [STORAGE_KEYS.enabled]: DEFAULT_ENABLED });
  return data[STORAGE_KEYS.enabled] !== false;
}

async function getPort() {
  const data = await storageGet({ [STORAGE_KEYS.port]: DEFAULT_PORT });
  const port = Number(data[STORAGE_KEYS.port]);
  return port > 1024 && port < 65535 ? port : DEFAULT_PORT;
}

async function getCaptureKey() {
  const data = await storageGet({ [STORAGE_KEYS.captureKey]: DEFAULT_CAPTURE_KEY });
  return String(data[STORAGE_KEYS.captureKey] || '').trim();
}

function ingestUrl(port) {
  return `http://127.0.0.1:${port}/v1/bubble/crawler/ingest`;
}

function writeIngestUrl(port) {
  return `http://127.0.0.1:${port}/v1/bubble/crawler/write-ingest`;
}

function healthUrl(port) {
  return `http://127.0.0.1:${port}/health`;
}

function buildHeaders(captureKey) {
  const headers = { 'Content-Type': 'application/json' };
  if (captureKey) headers['X-Bubble-MCP-Capture-Key'] = captureKey;
  return headers;
}

function normalizeEvent(kind, payload, result) {
  const appId = payload?.appId || payload?.requestBody?.appname || null;
  const endpoint = payload?.endpoint || null;
  const version = payload?.version || payload?.requestBody?.app_version || null;
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    kind,
    appId,
    version,
    endpoint,
    ok: Boolean(result?.ok),
    mode: result?.mode || 'local',
    reason: result?.reason || null,
    port: result?.port || null,
    capturedAt: payload?.capturedAt || Date.now(),
    deliveredAt: Date.now(),
  };
}

async function appendEvent(event) {
  const data = await storageGet({ [STORAGE_KEYS.eventLog]: [] });
  const current = Array.isArray(data[STORAGE_KEYS.eventLog]) ? data[STORAGE_KEYS.eventLog] : [];
  const next = [event, ...current].slice(0, MAX_EVENTS);
  await storageSet({ [STORAGE_KEYS.eventLog]: next });
}

function isMcpHealth(payload) {
  if (!payload || typeof payload !== 'object') return false;
  if (payload.ok === true && typeof payload.service === 'string') return true;
  if (payload.running === true && Object.prototype.hasOwnProperty.call(payload, 'sessionCount')) return true;
  if (payload.server === 'befree-bubble-mcp' || payload.name === 'befree-bubble-mcp') return true;
  return false;
}

function buildPortCandidates(hint) {
  const candidates = [];
  const seen = new Set();
  const add = (port) => {
    if (!Number.isInteger(port) || port <= 1024 || port >= 65535 || seen.has(port)) return;
    seen.add(port);
    candidates.push(port);
  };

  if (Number.isInteger(hint)) {
    for (let port = hint; port < hint + PORT_SCAN_RANGE; port += 1) add(port);
  }
  for (let port = DEFAULT_PORT; port < DEFAULT_PORT + PORT_SCAN_RANGE; port += 1) add(port);
  return candidates;
}

async function probeLocalPort(port) {
  try {
    const res = await fetch(healthUrl(port), { signal: AbortSignal.timeout(600) });
    if (!res.ok) return { ok: false, reason: 'health_unavailable' };

    let health = null;
    try { health = await res.json(); } catch { health = null; }
    if (isMcpHealth(health)) return { ok: true, health };

    const captureKey = await getCaptureKey();
    const ingestRes = await fetch(ingestUrl(port), {
      method: 'POST',
      headers: buildHeaders(captureKey),
      body: JSON.stringify({ _ping: true, source: 'befree-bubble-mcp-companion' }),
      signal: AbortSignal.timeout(900),
    });

    if (ingestRes.ok || ingestRes.status === 204) return { ok: true, health };
    if (ingestRes.status === 401 || ingestRes.status === 403) return { ok: false, reason: 'capture_key_rejected' };
    if (ingestRes.status === 404) return { ok: false, reason: 'missing_ingest' };
    return { ok: false, reason: 'unexpected_status', status: ingestRes.status };
  } catch {
    return { ok: false, reason: 'offline' };
  }
}

async function discoverLocalPort(hint) {
  for (const port of buildPortCandidates(hint)) {
    const probe = await probeLocalPort(port);
    if (probe.ok) {
      if (port !== hint) await storageSet({ [STORAGE_KEYS.port]: port });
      return { port, health: probe.health || null };
    }
    if (port === hint && probe.reason === 'capture_key_rejected') {
      return { port: null, reason: 'capture_key_rejected' };
    }
  }
  return { port: null, reason: 'local_offline' };
}

async function postLocal(pathBuilder, payload) {
  const savedPort = await getPort();
  const captureKey = await getCaptureKey();
  const { port, reason } = await discoverLocalPort(savedPort);
  if (!port) return { ok: false, reason: reason || 'local_offline' };

  try {
    const res = await fetch(pathBuilder(port), {
      method: 'POST',
      headers: buildHeaders(captureKey),
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(5_000),
    });
    if (res.ok || res.status === 204) return { ok: true, mode: 'local', port };
    const error = await res.text().catch(() => '');
    return {
      ok: false,
      reason: res.status === 401 || res.status === 403 ? 'capture_key_rejected' : 'local_error',
      status: res.status,
      error,
      port,
    };
  } catch (error) {
    return { ok: false, reason: 'local_error', error: error?.message || 'Local ingest failed.', port };
  }
}

async function sendStructureIngest(payload) {
  return postLocal(ingestUrl, payload);
}

async function sendWriteIngest(payload) {
  return postLocal(writeIngestUrl, payload);
}

async function handleCaptured(kind, payload) {
  stats.captured += 1;
  if (kind === 'write') stats.writes += 1;
  if (kind === 'structure') stats.structure += 1;

  const enabled = await getEnabled();
  if (!enabled) {
    const skipped = { ok: false, reason: 'disabled' };
    await appendEvent(normalizeEvent(kind, payload, skipped));
    return;
  }

  const result = kind === 'write'
    ? await sendWriteIngest(payload)
    : await sendStructureIngest(payload);

  if (result.ok) stats.sent += 1;
  else stats.errors += 1;
  await appendEvent(normalizeEvent(kind, payload, result));

  if (!result.ok) {
    console.warn('[Befree Bubble MCP Companion]', result.reason, result.error || '');
  }
}

async function checkConnection() {
  const startedAt = Date.now();
  const savedPort = await getPort();
  const local = await discoverLocalPort(savedPort);
  if (local.port) {
    return {
      connected: true,
      mode: 'local',
      port: local.port,
      latencyMs: Date.now() - startedAt,
      health: local.health || null,
    };
  }
  return { connected: false, mode: 'none', reason: local.reason || 'local_offline' };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'BUBBLE_API_CAPTURED') {
    handleCaptured('structure', message.payload).catch((error) => {
      stats.errors += 1;
      console.warn('[Befree Bubble MCP Companion]', error?.message || error);
    });
    return false;
  }

  if (message.type === 'BUBBLE_WRITE_CAPTURED') {
    handleCaptured('write', message.payload).catch((error) => {
      stats.errors += 1;
      console.warn('[Befree Bubble MCP Companion][write]', error?.message || error);
    });
    return false;
  }

  if (message.type === 'GET_ENABLED') {
    getEnabled().then((enabled) => sendResponse({ enabled }));
    return true;
  }

  if (message.type === 'SET_ENABLED') {
    storageSet({ [STORAGE_KEYS.enabled]: Boolean(message.enabled) }).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === 'GET_PORT') {
    getPort().then((port) => sendResponse({ port }));
    return true;
  }

  if (message.type === 'SET_PORT') {
    const port = Number(message.port);
    if (port > 1024 && port < 65535) {
      storageSet({ [STORAGE_KEYS.port]: port }).then(() => sendResponse({ ok: true }));
    } else {
      sendResponse({ ok: false, error: 'Invalid port' });
    }
    return true;
  }

  if (message.type === 'GET_CAPTURE_KEY') {
    getCaptureKey().then((captureKey) => sendResponse({ captureKey }));
    return true;
  }

  if (message.type === 'SET_CAPTURE_KEY') {
    storageSet({ [STORAGE_KEYS.captureKey]: String(message.captureKey || '').trim() })
      .then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === 'GET_STATS') {
    sendResponse({ stats: { ...stats } });
    return false;
  }

  if (message.type === 'GET_EVENTS') {
    storageGet({ [STORAGE_KEYS.eventLog]: [] }).then((data) => {
      const events = Array.isArray(data[STORAGE_KEYS.eventLog]) ? data[STORAGE_KEYS.eventLog] : [];
      sendResponse({ events });
    });
    return true;
  }

  if (message.type === 'CLEAR_EVENTS') {
    storageSet({ [STORAGE_KEYS.eventLog]: [] }).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === 'CHECK_MCP_CONNECTION') {
    checkConnection().then(sendResponse);
    return true;
  }

  return false;
});
