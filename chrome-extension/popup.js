'use strict';

const enabledToggle = document.getElementById('enabledToggle');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const mcpPortInput = document.getElementById('mcpPort');
const captureKeyInput = document.getElementById('captureKey');
const btnSavePort = document.getElementById('btnSavePort');
const btnSaveKey = document.getElementById('btnSaveKey');
const btnRefresh = document.getElementById('btnRefresh');
const btnClearEvents = document.getElementById('btnClearEvents');
const statCaptured = document.getElementById('statCaptured');
const statSent = document.getElementById('statSent');
const statWrites = document.getElementById('statWrites');
const statErrors = document.getElementById('statErrors');
const eventsList = document.getElementById('eventsList');

function msg(type, extra = {}) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type, ...extra }, resolve);
  });
}

function setStatus(state, text) {
  statusDot.className = `status-dot${state ? ` ${state}` : ''}`;
  statusText.textContent = text;
}

function formatTime(timestamp) {
  if (!timestamp) return '--:--:--';
  try {
    return new Date(timestamp).toLocaleTimeString();
  } catch {
    return '--:--:--';
  }
}

function renderEvents(events) {
  if (!Array.isArray(events) || events.length === 0) {
    eventsList.innerHTML = '<div class="empty">Nenhum evento recebido ainda.</div>';
    return;
  }

  eventsList.innerHTML = events.slice(0, 8).map((event) => {
    const kind = event.kind === 'write' ? 'write' : 'context';
    const ok = event.ok ? 'ok' : (event.reason || 'erro');
    const meta = [
      event.appId ? `app ${event.appId}` : null,
      event.version ? `version ${event.version}` : null,
      event.port ? `:${event.port}` : null,
      event.endpoint || null,
    ].filter(Boolean).join(' · ');

    return `
      <div class="event">
        <div class="event-top">
          <span>${kind}</span>
          <span>${ok} · ${formatTime(event.deliveredAt || event.capturedAt)}</span>
        </div>
        <div class="event-meta">${meta || 'sem metadados adicionais'}</div>
      </div>
    `;
  }).join('');
}

async function loadState() {
  const [{ enabled }, { port }, { captureKey }, { stats }, { events }] = await Promise.all([
    msg('GET_ENABLED'),
    msg('GET_PORT'),
    msg('GET_CAPTURE_KEY'),
    msg('GET_STATS'),
    msg('GET_EVENTS'),
  ]);

  enabledToggle.checked = enabled !== false;
  mcpPortInput.value = port || 3847;
  captureKeyInput.value = captureKey || '';

  statCaptured.textContent = stats?.captured ?? 0;
  statSent.textContent = stats?.sent ?? 0;
  statWrites.textContent = stats?.writes ?? 0;
  statErrors.textContent = stats?.errors ?? 0;
  renderEvents(events);
}

async function checkConnection() {
  setStatus('checking', 'Verificando serviço local...');
  const result = await msg('CHECK_MCP_CONNECTION');

  if (result?.connected) {
    const latency = result.latencyMs ? ` · ${result.latencyMs}ms` : '';
    setStatus('ok', `MCP local conectado em :${result.port}${latency}`);
    if (result.port) mcpPortInput.value = result.port;
    return;
  }

  if (result?.reason === 'capture_key_rejected') {
    setStatus('error', 'Serviço local rejeitou a capture key.');
    return;
  }

  setStatus('error', 'Serviço local não encontrado.');
}

enabledToggle.addEventListener('change', async () => {
  await msg('SET_ENABLED', { enabled: enabledToggle.checked });
  await loadState();
});

btnSavePort.addEventListener('click', async () => {
  const port = parseInt(mcpPortInput.value, 10);
  const result = await msg('SET_PORT', { port });
  if (result?.ok) {
    btnSavePort.textContent = 'Salvo';
    setTimeout(() => { btnSavePort.textContent = 'OK'; }, 1000);
    await checkConnection();
  }
});

mcpPortInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') btnSavePort.click();
});

btnSaveKey.addEventListener('click', async () => {
  await msg('SET_CAPTURE_KEY', { captureKey: captureKeyInput.value });
  btnSaveKey.textContent = 'Salva';
  setTimeout(() => { btnSaveKey.textContent = 'Salvar chave'; }, 1000);
  await checkConnection();
});

captureKeyInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') btnSaveKey.click();
});

btnRefresh.addEventListener('click', async () => {
  await loadState();
  await checkConnection();
});

btnClearEvents.addEventListener('click', async () => {
  await msg('CLEAR_EVENTS');
  await loadState();
});

(async () => {
  await loadState();
  await checkConnection();
})();
