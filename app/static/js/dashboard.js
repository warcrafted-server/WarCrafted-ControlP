const statsEl = document.getElementById('system-stats');
const gridEl = document.getElementById('instances-grid');
const feedbackEl = document.getElementById('action-feedback');
let feedbackTimeout = null;

function escapeHtml(text) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, (char) => map[char]);
}

function showFeedback(message, isError) {
  clearTimeout(feedbackTimeout);
  feedbackEl.textContent = message;
  feedbackEl.className = isError
    ? 'text-sm rounded-lg px-4 py-3 whitespace-pre-wrap bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-200 dark:border-red-800'
    : 'text-sm rounded-lg px-4 py-3 whitespace-pre-wrap bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:border-emerald-800';
  feedbackTimeout = setTimeout(() => feedbackEl.classList.add('hidden'), 8000);
}

function statCard(label, value, sub) {
  return `
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4">
      <p class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">${label}</p>
      <p class="text-2xl font-semibold mt-1">${value}</p>
      ${sub ? `<p class="text-xs text-gray-400 mt-1">${sub}</p>` : ''}
    </div>`;
}

function diffColorClass(ms) {
  if (ms == null) return 'text-gray-400';
  if (ms < 50) return 'text-emerald-500';
  if (ms <= 150) return 'text-amber-500';
  return 'text-rose-500';
}

const SERVER_STATE_META = {
  offline: { label: 'Detenido', dot: 'bg-gray-400' },
  starting: { label: 'Arrancando...', dot: 'bg-amber-500 animate-pulse' },
  online: { label: 'En linea', dot: 'bg-emerald-500' },
  stopping: { label: 'Deteniendo...', dot: 'bg-amber-500 animate-pulse' },
};

function serverCard(server) {
  if (server.error) {
    return `
      <div class="bg-white dark:bg-gray-900 rounded-xl border border-red-200 dark:border-red-900 p-4 flex flex-col gap-2">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-red-500"></span>
          <h3 class="font-medium">${escapeHtml(server.name)}</h3>
        </div>
        <p class="text-xs text-red-600 dark:text-red-400">${escapeHtml(server.error)}</p>
      </div>`;
  }

  const stateMeta = SERVER_STATE_META[server.state] || SERVER_STATE_META.offline;
  const typeLabel = server.type === 'playerbots' ? 'Playerbots' : 'AzerothCore';
  return `
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full ${stateMeta.dot}"></span>
          <div>
            <h3 class="font-medium leading-tight">${escapeHtml(server.name)}</h3>
            <p class="text-[11px] text-gray-400 leading-tight">${stateMeta.label}</p>
          </div>
        </div>
        <span class="text-xs px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-100">${typeLabel}</span>
      </div>
      <div class="grid grid-cols-4 gap-2 text-center text-sm">
        <div>
          <p class="text-gray-400 text-xs" title="Normalizado a 1 nucleo = 100%; un proceso multihilo puede superar el 100%.">CPU</p>
          <p class="font-medium">${server.cpu_percent != null ? server.cpu_percent + '%' : '-'}</p>
          ${server.cpu_percent_host != null ? `<p class="text-[10px] text-gray-400" title="Equivalente en % de la capacidad total del host, comparable con el CPU del host de arriba.">${server.cpu_percent_host}% host</p>` : ''}
        </div>
        <div>
          <p class="text-gray-400 text-xs">RAM</p>
          <p class="font-medium">${server.memory_mb != null ? server.memory_mb + ' MB' : '-'}</p>
        </div>
        <div>
          <p class="text-gray-400 text-xs">Jugadores</p>
          <p class="font-medium">${server.players_online != null ? server.players_online : '-'}</p>
        </div>
        <div>
          <p class="text-gray-400 text-xs" title="Retraso del bucle principal del worldserver (comando SOAP 'server info').">Diff</p>
          <p class="font-medium ${diffColorClass(server.update_diff_ms)}">${server.update_diff_ms != null ? server.update_diff_ms + ' ms' : '-'}</p>
        </div>
      </div>
      <div class="flex flex-col gap-2 mt-1">
        <div class="flex gap-2">
          <button data-action="start" data-id="${escapeHtml(server.id)}" data-name="${escapeHtml(server.name)}"
                  ${server.state !== 'offline' ? 'disabled' : ''}
                  class="flex-1 text-xs py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 ${server.state !== 'offline' ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}">
            Iniciar
          </button>
          <div class="flex-1 flex gap-1">
            <button data-action="stop" data-id="${escapeHtml(server.id)}" data-name="${escapeHtml(server.name)}"
                    ${server.state === 'offline' ? 'disabled' : ''}
                    class="flex-1 text-xs py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 ${server.state === 'offline' ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}">
              ${server.state === 'stopping' ? 'Forzar detencion' : 'Detener'}
            </button>
            <button data-action="scheduled-stop" data-id="${escapeHtml(server.id)}" data-name="${escapeHtml(server.name)}"
                    ${server.state !== 'online' ? 'disabled' : ''}
                    class="flex-1 text-xs py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 ${server.state !== 'online' ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}">
              Parada programada
            </button>
          </div>
        </div>
        <div class="flex gap-2">
          <a href="/console/${server.id}"
             class="flex-1 text-xs py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-center">
            Consola
          </a>
          <button data-action="log" data-id="${escapeHtml(server.id)}" data-name="${escapeHtml(server.name)}"
                  class="flex-1 text-xs py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-100 dark:hover:bg-gray-800">
            Logs
          </button>
        </div>
      </div>
    </div>`;
}

async function refreshStats() {
  try {
    const response = await fetch('/api/system/stats');
    if (!response.ok) return;
    const data = await response.json();
    statsEl.innerHTML = [
      statCard('CPU del host', data.cpu_percent + '%'),
      statCard('Memoria', data.memory_percent + '%', `${data.memory_used_mb} / ${data.memory_total_mb} MB`),
      statCard('Disco', data.disk_percent + '%'),
    ].join('');
  } catch (err) {
    // se reintenta en el siguiente ciclo de refresco
  }
}

function linkedInstancesLabel(names) {
  if (!names.length) return 'Sin reinos asociados';
  const label = names.length > 1 ? 'Reinos asociados' : 'Reino asociado';
  return `${label}: ${names.map(escapeHtml).join(', ')}`;
}

function authServiceCard(service) {
  const stateMeta = SERVER_STATE_META[service.state] || SERVER_STATE_META.offline;
  return `
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full ${stateMeta.dot}"></span>
          <div>
            <h3 class="font-medium leading-tight">${escapeHtml(service.name)}</h3>
            <p class="text-[11px] text-gray-400 leading-tight">${stateMeta.label}</p>
          </div>
        </div>
        <span class="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300">Authserver</span>
      </div>
      <p class="text-xs text-gray-500 dark:text-gray-400">${linkedInstancesLabel(service.linked_instances)}</p>
      <div class="grid grid-cols-2 gap-2 text-center text-sm">
        <div>
          <p class="text-gray-400 text-xs">Cuentas creadas</p>
          <p class="font-medium">${service.accounts_total != null ? service.accounts_total : '-'}</p>
        </div>
        <div>
          <p class="text-gray-400 text-xs">Cuentas conectadas</p>
          <p class="font-medium">${service.accounts_online != null ? service.accounts_online : '-'}</p>
        </div>
      </div>
      <div class="flex gap-2 mt-1">
        <button data-kind="auth" data-action="start" data-id="${escapeHtml(service.id)}" data-name="${escapeHtml(service.name)}"
                ${service.state !== 'offline' ? 'disabled' : ''}
                class="flex-1 text-xs py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 ${service.state !== 'offline' ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}">
          Iniciar
        </button>
        <button data-kind="auth" data-action="stop" data-id="${escapeHtml(service.id)}" data-name="${escapeHtml(service.name)}"
                ${service.state === 'offline' ? 'disabled' : ''}
                class="flex-1 text-xs py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 ${service.state === 'offline' ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-100 dark:hover:bg-gray-800'}">
          Detener
        </button>
      </div>
    </div>`;
}

// Intercala cada tarjeta de authserver con las de los reinos que le apuntan
// (auth_service_id), en vez de dos rejillas separadas: un authserver privado
// (1 reino) queda emparejado en su misma fila; uno compartido (2+) encabeza
// el grupo seguido de todos sus reinos. Las columnas se ajustan al grupo mas
// grande para que cada grupo ocupe una fila limpia, igual que las 3 tarjetas
// de metricas del host de arriba.
function renderInstancesGrid(servers, authServices) {
  if (!servers.length) {
    gridEl.className = 'grid grid-cols-1 gap-4';
    gridEl.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400">No hay instancias configuradas en el .env.</p>';
    return;
  }

  const serversByAuthId = new Map();
  servers.forEach((server) => {
    const key = server.auth_service_id || `__sin-auth-${server.id}`;
    if (!serversByAuthId.has(key)) serversByAuthId.set(key, []);
    serversByAuthId.get(key).push(server);
  });

  const cards = [];
  const usedKeys = new Set();
  let maxGroupSize = 1;

  authServices.forEach((service) => {
    const group = serversByAuthId.get(service.id) || [];
    usedKeys.add(service.id);
    cards.push(authServiceCard(service));
    group.forEach((server) => cards.push(serverCard(server)));
    maxGroupSize = Math.max(maxGroupSize, 1 + group.length);
  });

  // Reinos sin servicio en /auth-services (no deberia pasar: toda instancia
  // habilitada tiene al menos su authserver implicito) o con config invalida
  // (auth_service_id vacio): se muestran sueltos al final, sin perderlos.
  serversByAuthId.forEach((group, key) => {
    if (usedKeys.has(key)) return;
    group.forEach((server) => cards.push(serverCard(server)));
  });

  const cols = Math.min(maxGroupSize, 4);
  gridEl.className = `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-${cols} gap-4`;
  gridEl.innerHTML = cards.join('');
}

async function refreshServers() {
  try {
    const [serversRes, authRes] = await Promise.all([
      fetch('/api/servers'),
      fetch('/api/servers/auth-services'),
    ]);
    if (serversRes.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (!serversRes.ok || !authRes.ok) return;
    const servers = await serversRes.json();
    const authServices = await authRes.json();
    renderInstancesGrid(servers, authServices);
  } catch (err) {
    // se reintenta en el siguiente ciclo de refresco
  }
}

const logModal = document.getElementById('log-modal');
const logModalTitle = document.getElementById('log-modal-title');
const logModalSelect = document.getElementById('log-modal-select');
const logModalLiveBtn = document.getElementById('log-modal-live');
const logModalCopyBtn = document.getElementById('log-modal-copy');
const logModalDownloadBtn = document.getElementById('log-modal-download');
const logModalTruncated = document.getElementById('log-modal-truncated');
const logModalContent = document.getElementById('log-modal-content');

const LOG_CATEGORY_LABELS = {
  worldserver: 'Consola',
  server: 'Servidor',
  errors: 'Errores',
  playerbots: 'Playerbots',
  gm: 'GM',
  chat: 'Chat',
};

// Limite de lineas en "ver en vivo": sin esto, una sesion larga acumula el
// contenido en memoria/DOM sin fin y el navegador acaba igual de bloqueado
// que con un archivo historico gigante.
const LIVE_MAX_LINES = 2000;

let logInstanceId = null;
let logSocket = null;
let liveLines = [];

function logCategoryLabel(category) {
  return LOG_CATEGORY_LABELS[category] || category;
}

function logRunLabel(run) {
  const when = run.started_at.replace('_', ' ');
  if (run.source === 'nativo') {
    return `${run.category} — modificado ${when}`;
  }
  return `${logCategoryLabel(run.category)} — ${when}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function updateDownloadLink(filename) {
  if (filename) {
    logModalDownloadBtn.href = `/api/servers/${logInstanceId}/logs/${encodeURIComponent(filename)}/download`;
    logModalDownloadBtn.classList.remove('pointer-events-none', 'opacity-50');
  } else {
    logModalDownloadBtn.href = '#';
    logModalDownloadBtn.classList.add('pointer-events-none', 'opacity-50');
  }
}

function appendLogLine(line) {
  const atBottom = logModalContent.scrollHeight - logModalContent.scrollTop - logModalContent.clientHeight < 40;
  liveLines.push(line);
  if (liveLines.length > LIVE_MAX_LINES) liveLines.splice(0, liveLines.length - LIVE_MAX_LINES);
  logModalContent.textContent = liveLines.join('\n');
  if (atBottom) logModalContent.scrollTop = logModalContent.scrollHeight;
}

function stopLiveLog() {
  if (logSocket) {
    logSocket.close();
    logSocket = null;
  }
  logModalSelect.disabled = false;
  logModalLiveBtn.textContent = 'Ver en vivo';
  logModalLiveBtn.classList.remove('bg-brand-600', 'hover:bg-brand-700', 'text-white', 'border-transparent');
}

function startLiveLog() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  logSocket = new WebSocket(`${protocol}://${window.location.host}/ws/servers/${logInstanceId}/logs`);
  logModalSelect.disabled = true;
  logModalLiveBtn.textContent = 'Detener vivo';
  logModalLiveBtn.classList.add('bg-brand-600', 'hover:bg-brand-700', 'text-white', 'border-transparent');
  logModalTruncated.classList.add('hidden');
  liveLines = [];
  logModalContent.textContent = '';

  logSocket.addEventListener('message', (event) => appendLogLine(event.data));
  logSocket.addEventListener('close', () => stopLiveLog());
}

async function loadSelectedLog() {
  if (!logInstanceId || !logModalSelect.value) return;
  const filename = logModalSelect.value;
  updateDownloadLink(filename);
  logModalTruncated.classList.add('hidden');
  logModalContent.textContent = 'Cargando...';
  try {
    const response = await fetch(`/api/servers/${logInstanceId}/logs/${encodeURIComponent(filename)}`);
    if (!response.ok) {
      logModalContent.textContent = 'No se pudo cargar este archivo de log.';
      return;
    }
    const data = await response.json();
    logModalContent.textContent = data.content || '(archivo vacio)';
    if (data.truncated) {
      logModalTruncated.textContent =
        `Mostrando solo el final del archivo (${formatBytes(data.total_size_bytes)} en total). `
        + 'Descarga el archivo completo para verlo entero.';
      logModalTruncated.classList.remove('hidden');
    }
  } catch (err) {
    logModalContent.textContent = 'Error de conexion al cargar el log.';
  }
}

async function openLogModal(id, name) {
  logInstanceId = id;
  logModalTitle.textContent = `Logs — ${name}`;
  logModalContent.textContent = 'Cargando...';
  logModalTruncated.classList.add('hidden');
  logModalSelect.innerHTML = '';
  updateDownloadLink(null);
  logModal.classList.remove('hidden');

  try {
    const response = await fetch(`/api/servers/${id}/logs`);
    const runs = response.ok ? await response.json() : [];
    if (!runs.length) {
      logModalContent.textContent = 'Todavia no hay logs guardados para esta instancia.';
      return;
    }
    const option = (run) => `<option value="${escapeHtml(run.filename)}">${escapeHtml(logRunLabel(run))}</option>`;
    const historico = runs.filter((run) => run.source !== 'nativo');
    const nativo = runs.filter((run) => run.source === 'nativo');
    logModalSelect.innerHTML = [
      historico.length ? `<optgroup label="Historico">${historico.map(option).join('')}</optgroup>` : '',
      nativo.length ? `<optgroup label="AzerothCore (en vivo)">${nativo.map(option).join('')}</optgroup>` : '',
    ].join('');
    await loadSelectedLog();
  } catch (err) {
    logModalContent.textContent = 'Error de conexion al listar los logs.';
  }
}

function closeLogModal() {
  stopLiveLog();
  logInstanceId = null;
  logModal.classList.add('hidden');
}

logModalSelect.addEventListener('change', () => {
  if (logSocket) stopLiveLog();
  loadSelectedLog();
});

logModalLiveBtn.addEventListener('click', () => {
  if (logSocket) {
    stopLiveLog();
    loadSelectedLog();
  } else {
    startLiveLog();
  }
});

logModalCopyBtn.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(logModalContent.textContent);
    const original = logModalCopyBtn.textContent;
    logModalCopyBtn.textContent = 'Copiado';
    setTimeout(() => { logModalCopyBtn.textContent = original; }, 1500);
  } catch (err) {
    showFeedback('No se pudo copiar el log al portapapeles.', true);
  }
});

document.getElementById('log-modal-close').addEventListener('click', closeLogModal);
logModal.addEventListener('click', (event) => {
  if (event.target === logModal) closeLogModal();
});

async function handleActionClick(button, urlFor, extraLabel) {
  const { action, id, name } = button.dataset;
  const actionLabel = (action === 'start' ? 'iniciar' : 'detener') + extraLabel;
  button.disabled = true;
  try {
    const response = await fetch(urlFor(id, action), { method: 'POST' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      showFeedback(`No se pudo ${actionLabel} "${name}": ${data.detail || 'error desconocido'}`, true);
    } else if (data.detail) {
      showFeedback(`${name}: ${data.detail}`, data.success === false);
    }
    await refreshServers();
  } catch (err) {
    showFeedback(`Error de conexion al intentar ${actionLabel} "${name}".`, true);
  } finally {
    button.disabled = false;
  }
}

// --- parada programada (delay + mensaje simultaneo por chat y pantalla) ---
const scheduledStopModal = document.getElementById('scheduled-stop-modal');
const scheduledStopTitle = document.getElementById('scheduled-stop-title');
const scheduledStopHours = document.getElementById('scheduled-stop-hours');
const scheduledStopMinutes = document.getElementById('scheduled-stop-minutes');
const scheduledStopSeconds = document.getElementById('scheduled-stop-seconds');
const scheduledStopMessage = document.getElementById('scheduled-stop-message');
const scheduledStopConfirm = document.getElementById('scheduled-stop-confirm');
let scheduledStopTarget = null;

function openScheduledStopModal(id, name) {
  scheduledStopTarget = { id, name };
  scheduledStopTitle.textContent = `Parada programada — ${name}`;
  scheduledStopHours.value = '0';
  scheduledStopMinutes.value = '10';
  scheduledStopSeconds.value = '0';
  scheduledStopMessage.value = '';
  scheduledStopConfirm.disabled = false;
  scheduledStopConfirm.textContent = 'Programar parada';
  scheduledStopModal.classList.remove('hidden');
}

function closeScheduledStopModal() {
  scheduledStopTarget = null;
  scheduledStopModal.classList.add('hidden');
}

document.getElementById('scheduled-stop-close').addEventListener('click', closeScheduledStopModal);
document.getElementById('scheduled-stop-cancel').addEventListener('click', closeScheduledStopModal);
scheduledStopModal.addEventListener('click', (event) => {
  if (event.target === scheduledStopModal) closeScheduledStopModal();
});

scheduledStopConfirm.addEventListener('click', async () => {
  if (!scheduledStopTarget) return;
  const hours = parseInt(scheduledStopHours.value || '0', 10);
  const minutes = parseInt(scheduledStopMinutes.value || '0', 10);
  const seconds = parseInt(scheduledStopSeconds.value || '0', 10);
  const delaySeconds = hours * 3600 + minutes * 60 + seconds;
  const message = scheduledStopMessage.value.trim();
  if (delaySeconds <= 0) {
    showFeedback('Indica un tiempo de espera mayor que 0.', true);
    return;
  }
  if (!message) {
    showFeedback('Escribe un mensaje para avisar a los jugadores.', true);
    return;
  }
  const { id, name } = scheduledStopTarget;
  scheduledStopConfirm.disabled = true;
  scheduledStopConfirm.textContent = 'Programando...';
  try {
    const response = await fetch(`/api/servers/${id}/scheduled-stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delay_seconds: delaySeconds, message }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      showFeedback(`No se pudo programar la parada de "${name}": ${data.detail || 'error desconocido'}`, true);
    } else {
      showFeedback(`${name}: ${data.detail || 'Parada programada.'}`, data.success === false);
      closeScheduledStopModal();
    }
    await refreshServers();
  } catch (err) {
    showFeedback(`Error de conexion al programar la parada de "${name}".`, true);
  } finally {
    scheduledStopConfirm.disabled = false;
    scheduledStopConfirm.textContent = 'Programar parada';
  }
});

gridEl.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  if (button.dataset.action === 'log') {
    openLogModal(button.dataset.id, button.dataset.name);
    return;
  }
  if (button.dataset.action === 'scheduled-stop') {
    openScheduledStopModal(button.dataset.id, button.dataset.name);
    return;
  }
  if (button.dataset.kind === 'auth') {
    await handleActionClick(button, (id, action) => `/api/servers/auth-services/${id}/${action}`, ' authserver');
    return;
  }
  await handleActionClick(button, (id, action) => `/api/servers/${id}/${action}`, '');
});

document.getElementById('logout-btn').addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login';
});

const pluginsMenuBtn = document.getElementById('plugins-menu-btn');
const pluginsMenu = document.getElementById('plugins-menu');

function pluginMenuItem(plugin) {
  const icon = plugin.icon ? `<i class="fa-solid ${escapeHtml(plugin.icon)} w-4 text-center text-gray-400"></i>` : '';
  return `
    <a href="${escapeHtml(plugin.route)}" class="flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800">
      ${icon}
      ${escapeHtml(plugin.title)}
    </a>`;
}

async function loadPluginsMenu() {
  try {
    const response = await fetch('/api/v1/plugins/');
    if (!response.ok) {
      pluginsMenu.innerHTML = '<p class="px-3 py-2 text-sm text-gray-400">No se pudo cargar los plugins</p>';
      return;
    }
    const pluginsList = await response.json();
    const withUi = pluginsList.filter((plugin) => plugin.has_ui && plugin.route);
    pluginsMenu.innerHTML = withUi.length
      ? withUi.map(pluginMenuItem).join('')
      : '<p class="px-3 py-2 text-sm text-gray-400">Sin plugins con interfaz</p>';
  } catch (err) {
    pluginsMenu.innerHTML = '<p class="px-3 py-2 text-sm text-gray-400">No se pudo cargar los plugins</p>';
  }
}

pluginsMenuBtn.addEventListener('click', (event) => {
  event.stopPropagation();
  pluginsMenu.classList.toggle('hidden');
});
document.addEventListener('click', () => pluginsMenu.classList.add('hidden'));

async function checkUpdates() {
  const badge = document.getElementById('store-update-badge');
  let count = 0;
  const parts = [];

  try {
    const response = await fetch('/api/v1/plugins/catalog');
    if (response.ok) {
      const data = await response.json();
      if (data.configured) {
        const updates = data.plugins.filter((plugin) => plugin.update_available);
        if (updates.length) {
          count += updates.length;
          parts.push(`${updates.length} plugin(s)`);
        }
      }
    }
  } catch (err) {
    // la tienda no es critica para el dashboard; se ignora en silencio
  }

  try {
    const response = await fetch('/api/system/update-check');
    if (response.ok) {
      const data = await response.json();
      if (data.configured && data.update_available) {
        count += 1;
        parts.push('el panel principal');
      }
    }
  } catch (err) {
    // idem
  }

  if (count) {
    badge.textContent = count;
    badge.title = `Hay actualizaciones disponibles: ${parts.join(' y ')}`;
    badge.classList.remove('hidden');
  }
}

refreshStats();
refreshServers();
loadPluginsMenu();
checkUpdates();
setInterval(refreshStats, 5000);
setInterval(refreshServers, 5000);
