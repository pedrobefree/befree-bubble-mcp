/**
 * Befree Bubble MCP Companion — Content Script
 *
 * Runs in MAIN world (same JS context as the Bubble editor page).
 * Monkey-patches window.fetch and XMLHttpRequest to intercept responses
 * from Bubble's internal API endpoints:
 *   - /appeditor/load_multiple_paths/...
 *   - /appeditor/load_single_path/...
 *   - /appeditor/write
 *
 * Captured payloads are forwarded to the background service worker via
 * window.postMessage (since content scripts in MAIN world cannot use
 * chrome.runtime directly without a bridge).
 *
 * The background worker then POSTs the data to the local MCP companion server at
 * POST http://127.0.0.1:<port>/v1/bubble/crawler/ingest
 */

(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────────────────

  const MCP_MSG_TYPE = '__befree_bubble_mcp_crawl__';
  const MCP_WRITE_MSG_TYPE = '__befree_bubble_mcp_write__';
  const MCP_PAGE_CATALOG_ENDPOINT = '__befree_bubble_mcp_page_catalog__';

  // Endpoints we care about.
  // load_multiple_paths always has the /appeditor/ prefix.
  // load_single_path does NOT — it's served directly at /load_single_path/.
  const INTERCEPT_PATTERNS = [
    /\/load_multiple_paths\//,
    /\/load_single_path\//,
  ];
  const WRITE_INTERCEPT_PATTERN = /\/appeditor\/write(?:[/?#]|$)/;
  const POTENTIAL_MUTATION_PATTERN = /\/appeditor\/(?!load_multiple_paths|load_single_path|calculate_derived|load_path_version_hashes)/;

  function shouldIntercept(url) {
    return INTERCEPT_PATTERNS.some((re) => re.test(url));
  }

  function shouldInterceptWrite(url) {
    return WRITE_INTERCEPT_PATTERN.test(url);
  }

  function shouldInterceptPotentialMutation(url, method) {
    const normalizedMethod = String(method || 'GET').toUpperCase();
    if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(normalizedMethod)) return false;
    return POTENTIAL_MUTATION_PATTERN.test(url);
  }

  /**
   * Extract appId and version from URL like:
   *   /appeditor/load_multiple_paths/{appId}/{version}
   *   /appeditor/load_single_path/{appId}/{version}/{hash}/...
   */
  function parseBubbleUrl(url) {
    const m = url.match(/\/(?:appeditor\/)?(?:load_multiple_paths|load_single_path)\/([^/]+)\/([^/]+)/);
    if (!m) return null;
    return { appId: m[1], version: m[2] };
  }

  function send(type, payload) {
    window.postMessage({ type, payload }, '*');
  }

  function getCurrentAppId() {
    try {
      return String(new URL(window.location.href).searchParams.get('id') || '').trim();
    } catch (_) {
      return '';
    }
  }

  function getCurrentBubbleVersion() {
    try {
      return String(new URL(window.location.href).searchParams.get('version') || '').trim() || null;
    } catch (_) {
      return null;
    }
  }

  function getVisibleEditorLines() {
    const bodyText = String(document.body?.innerText || '');
    if (!bodyText) return [];

    return bodyText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function collectSectionNames(lines, startPattern, stopPattern, options = {}) {
    const startIndex = lines.findIndex((line) => startPattern.test(line));
    if (startIndex < 0) return [];

    const ignoredPattern = options.ignoredPattern || /^(web pages|reusable elements?|backend workflows?|new page|add page|search|type to search|page)$/i;
    const names = [];
    const seen = new Set();

    for (const line of lines.slice(startIndex + 1)) {
      if (stopPattern.test(line)) break;
      if (ignoredPattern.test(line)) continue;
      if (line.length > 80) continue;
      if (/[{}()[\]]/.test(line)) continue;

      const normalized = line.toLowerCase();
      if (seen.has(normalized)) continue;
      seen.add(normalized);
      names.push(line);
    }

    return names;
  }

  function collectVisiblePageNames(lines = getVisibleEditorLines()) {
    const names = collectSectionNames(
      lines,
      /^web pages$/i,
      /^(reusable elements?|backend workflows?|styles?|data|database|option sets?|plugins?|logs?|settings?|design|workflow|element tree|layers|appearance|layout|conditional)$/i,
    );
    if (names.length < 2) return [];
    if (!names.some((name) => ['index', '404'].includes(name.toLowerCase()))) return [];
    return names;
  }

  function collectVisibleReusableNames(lines = getVisibleEditorLines()) {
    return collectSectionNames(
      lines,
      /^reusable elements?$/i,
      /^(web pages|backend workflows?|styles?|data|database|option sets?|plugins?|logs?|settings?|design|workflow|element tree|layers|appearance|layout|conditional)$/i,
    );
  }

  function collectVisibleBackendWorkflowNames(lines = getVisibleEditorLines()) {
    return collectSectionNames(
      lines,
      /^backend workflows?$/i,
      /^(web pages|reusable elements?|styles?|data|database|option sets?|plugins?|logs?|settings?|design|workflow|element tree|layers|appearance|layout|conditional)$/i,
    );
  }

  function inferActiveEditorArea(lines = getVisibleEditorLines()) {
    const areas = ['Design', 'Workflow', 'Responsive', 'Data', 'Styles', 'Plugins', 'Settings', 'Logs'];
    return areas.find((area) => lines.some((line) => line.toLowerCase() === area.toLowerCase())) || null;
  }

  function inferActiveContextName(lines, pages, reusables) {
    const candidates = [...pages, ...reusables]
      .map((name) => String(name || '').trim())
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);
    for (const line of lines.slice(0, 40)) {
      for (const candidate of candidates) {
        if (line === candidate || line.startsWith(`${candidate} `) || line.includes(` ${candidate} `)) {
          return candidate;
        }
      }
    }
    return null;
  }

  let lastPageCatalogSignature = '';
  let pageCatalogTimer = null;

  function sendPageCatalogSnapshot() {
    pageCatalogTimer = null;
    const appId = getCurrentAppId();
    if (!appId) return;

    const lines = getVisibleEditorLines();
    const names = collectVisiblePageNames(lines);
    if (names.length < 2) return;
    const reusables = collectVisibleReusableNames(lines);
    const backendWorkflows = collectVisibleBackendWorkflowNames(lines);

    const signature = `${appId}:${names.join('|')}:${reusables.join('|')}:${backendWorkflows.join('|')}`;
    if (signature === lastPageCatalogSignature) return;
    lastPageCatalogSignature = signature;

    send(MCP_MSG_TYPE, {
      endpoint: MCP_PAGE_CATALOG_ENDPOINT,
      appId,
      version: getCurrentBubbleVersion(),
      requestBody: null,
      responseData: {
        pageCatalog: {
          names,
          url: window.location.href,
        },
        editorDomSnapshot: {
          pages: names,
          reusables,
          backendWorkflows,
          activeContextName: inferActiveContextName(lines, names, reusables),
          activeEditorArea: inferActiveEditorArea(lines),
          url: window.location.href,
          title: document.title || null,
        },
      },
      capturedAt: Date.now(),
    });
  }

  function schedulePageCatalogSnapshot(delayMs = 1200) {
    if (pageCatalogTimer) clearTimeout(pageCatalogTimer);
    pageCatalogTimer = setTimeout(sendPageCatalogSnapshot, delayMs);
  }

  function buildWritePayload(url, requestBody, responseData, options) {
    const appId = String(requestBody?.appname || requestBody?.appId || getCurrentAppId() || '').trim();
    const changes = Array.isArray(requestBody?.changes) ? requestBody.changes : [];
    const refreshOnly = Boolean(options?.refreshOnly);
    if (!appId || (!refreshOnly && changes.length === 0)) {
      return null;
    }

    return {
      endpoint: url,
      appId,
      version: String(requestBody?.app_version || '').trim() || null,
      requestBody,
      responseData,
      refreshOnly,
      method: options?.method || null,
      capturedAt: Date.now(),
    };
  }

  // ── Fetch interception ─────────────────────────────────────────────────────

  const _origFetch = window.fetch;

  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : (input instanceof Request ? input.url : String(input));
    const method = String(init?.method || (input instanceof Request ? input.method : 'GET') || 'GET').toUpperCase();

    const interceptStructure = shouldIntercept(url);
    const interceptWrite = shouldInterceptWrite(url);
    const interceptPotentialMutation = !interceptWrite && shouldInterceptPotentialMutation(url, method);

    if (!interceptStructure && !interceptWrite && !interceptPotentialMutation) {
      return _origFetch.apply(this, arguments);
    }

    let requestBody = null;
    try {
      if (init?.body) {
        if (typeof init.body === 'string') requestBody = JSON.parse(init.body);
        else if (init.body instanceof FormData || init.body instanceof URLSearchParams) {
          requestBody = Object.fromEntries(init.body.entries());
        }
      }
    } catch (_) {}

    const response = await _origFetch.apply(this, arguments);

    // Clone so we can read body without consuming the original
    const clone = response.clone();
    clone.json().then((data) => {
      if (interceptStructure) {
        const meta = parseBubbleUrl(url);
        if (!meta) return;
        send(MCP_MSG_TYPE, {
          endpoint: url,
          appId: meta.appId,
          version: meta.version,
          requestBody,
          responseData: data,
          capturedAt: Date.now(),
        });
        return;
      }

      if ((interceptWrite || interceptPotentialMutation) && response.ok) {
        const payload = buildWritePayload(url, requestBody, data, {
          method,
          refreshOnly: interceptPotentialMutation || !Array.isArray(requestBody?.changes),
        });
        if (payload) send(MCP_WRITE_MSG_TYPE, payload);
      }
    }).catch(() => {});

    return response;
  };

  // ── XHR interception ───────────────────────────────────────────────────────

  const _origXHROpen = XMLHttpRequest.prototype.open;
  const _origXHRSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this._mcpUrl = String(url);
    this._mcpMethod = String(method || 'GET').toUpperCase();
    return _origXHROpen.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.send = function (body) {
    const url = this._mcpUrl || '';
    const method = this._mcpMethod || 'GET';

    const interceptStructure = shouldIntercept(url);
    const interceptWrite = shouldInterceptWrite(url);
    const interceptPotentialMutation = !interceptWrite && shouldInterceptPotentialMutation(url, method);

    if (interceptStructure || interceptWrite || interceptPotentialMutation) {
      let requestBody = null;
      try { requestBody = body ? JSON.parse(body) : null; } catch (_) {}

      this.addEventListener('load', () => {
        try {
          const data = JSON.parse(this.responseText);
          if (interceptStructure) {
            const meta = parseBubbleUrl(url);
            if (!meta) return;
            send(MCP_MSG_TYPE, {
              endpoint: url,
              appId: meta.appId,
              version: meta.version,
              requestBody,
              responseData: data,
              capturedAt: Date.now(),
            });
            return;
          }

          if ((interceptWrite || interceptPotentialMutation) && this.status >= 200 && this.status < 300) {
            const payload = buildWritePayload(url, requestBody, data, {
              method,
              refreshOnly: interceptPotentialMutation || !Array.isArray(requestBody?.changes),
            });
            if (payload) send(MCP_WRITE_MSG_TYPE, payload);
          }
        } catch (_) {}
      });
    }

    return _origXHRSend.apply(this, arguments);
  };

  // ── Bridge: forward postMessage to extension background ───────────────────

  function startPageCatalogObserver() {
    setTimeout(sendPageCatalogSnapshot, 1500);
    setTimeout(sendPageCatalogSnapshot, 4000);

    if (!document.body || typeof MutationObserver === 'undefined') return;
    const observer = new MutationObserver(() => schedulePageCatalogSnapshot(1500));
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startPageCatalogObserver, { once: true });
  } else {
    startPageCatalogObserver();
  }

  // A separate (isolated-world) bridge picks this up.
  // We inject a tiny isolated-world listener via the background service worker
  // using chrome.scripting.executeScript. That listener listens for
  // MCP_MSG_TYPE on window and relays to chrome.runtime.sendMessage.
  // This avoids the MAIN↔isolated-world chrome.runtime restriction.

})();
