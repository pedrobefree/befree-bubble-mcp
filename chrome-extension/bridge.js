/**
 * Befree Bubble MCP Companion — Bridge Script (isolated world)
 *
 * Injected at document_start in the ISOLATED world.
 * Listens for window.postMessage from the MAIN world content script,
 * then relays the payload to the background service worker via
 * chrome.runtime.sendMessage.
 *
 * This is the solution to the MAIN↔isolated-world messaging restriction:
 * only isolated-world scripts have access to chrome.runtime.
 */

(function () {
  'use strict';

  const MCP_MSG_TYPE = '__befree_bubble_mcp_crawl__';
  const MCP_WRITE_MSG_TYPE = '__befree_bubble_mcp_write__';

  window.addEventListener('message', (event) => {
    // Only accept messages from our own content script (same origin, same window)
    if (event.source !== window) return;
    if (!event.data || ![MCP_MSG_TYPE, MCP_WRITE_MSG_TYPE].includes(event.data.type)) return;

    const payload = event.data.payload;
    if (!payload) return;

    const messageType = event.data.type === MCP_WRITE_MSG_TYPE
      ? 'BUBBLE_WRITE_CAPTURED'
      : 'BUBBLE_API_CAPTURED';

    chrome.runtime.sendMessage({ type: messageType, payload }).catch(() => {
      // Background may not be ready yet; silently ignore
    });
  });
})();
