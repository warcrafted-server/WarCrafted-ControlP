const feedbackEl = document.getElementById('action-feedback');
const catalogLoadingEl = document.getElementById('catalog-loading');
const emptyStateEl = document.getElementById('empty-state');
const gridEl = document.getElementById('catalog-grid');
const tokenStatusEl = document.getElementById('token-status');
const updatesStatusEl = document.getElementById('updates-status');
const tokenModal = document.getElementById('token-modal');
const tokenInput = document.getElementById('token-input');
const tokenModalError = document.getElementById('token-modal-error');
const panelUpdateCard = document.getElementById('panel-update-card');
const panelVersionText = document.getElementById('panel-version-text');
const panelUpdateAction = document.getElementById('panel-update-action');
const panelUpdateLog = document.getElementById('panel-update-log');
const updateConfirmModal = document.getElementById('update-confirm-modal');
const updateConfirmTitle = document.getElementById('update-confirm-title');
const updateConfirmSubtitle = document.getElementById('update-confirm-subtitle');
const updateConfirmChangelog = document.getElementById('update-confirm-changelog');
const updateConfirmPostpone = document.getElementById('update-confirm-postpone');
const updateConfirmAccept = document.getElementById('update-confirm-accept');
let feedbackTimeout = null;
let catalogBySlug = {};
let lastPanelUpdateInfo = null;

function confirmUpdate({ title, fromVersion, toVersion, changelog }) {
  return new Promise((resolve) => {
    updateConfirmTitle.textContent = title;
    updateConfirmSubtitle.textContent = fromVersion
      ? `Version instalada: v${fromVersion} → disponible: v${toVersion}`
      : `Nueva version: v${toVersion}`;
    updateConfirmChangelog.textContent = changelog && changelog.trim()
      ? changelog.trim()
      : 'No hay notas para esta version. Puedes revisar el repositorio si quieres mas detalle antes de actualizar.';
    updateConfirmModal.classList.remove('hidden');

    function cleanup(result) {
      updateConfirmModal.classList.add('hidden');
      updateConfirmAccept.removeEventListener('click', onAccept);
      updateConfirmPostpone.removeEventListener('click', onPostpone);
      resolve(result);
    }
    function onAccept() { cleanup(true); }
    function onPostpone() { cleanup(false); }

    updateConfirmAccept.addEventListener('click', onAccept);
    updateConfirmPostpone.addEventListener('click', onPostpone);
  });
}

function escapeHtml(text) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, (char) => map[char]);
}

function showFeedback(message, isError) {
  clearTimeout(feedbackTimeout);
  feedbackEl.textContent = message;
  feedbackEl.classList.remove('hidden');
  feedbackEl.className = isError
    ? 'text-sm rounded-lg px-4 py-3 whitespace-pre-wrap bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/30 dark:text-red-200 dark:border-red-800'
    : 'text-sm rounded-lg px-4 py-3 whitespace-pre-wrap bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:border-emerald-800';
  feedbackTimeout = setTimeout(() => feedbackEl.classList.add('hidden'), 8000);
}

function openTokenModal() {
  tokenInput.value = '';
  tokenModalError.classList.add('hidden');
  tokenModal.classList.remove('hidden');
  tokenInput.focus();
}

function closeTokenModal() {
  tokenModal.classList.add('hidden');
}

function actionHtmlFor(plugin) {
  if (!plugin.installed) {
    return `<button data-action="install" data-slug="${escapeHtml(plugin.slug)}"
               class="text-xs px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white">
         Instalar
       </button>`;
  }
  if (plugin.update_available) {
    return `
      <span class="text-xs px-2 py-1 rounded-full bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200">
        v${escapeHtml(plugin.installed_version)} instalada
      </span>
      <button data-action="update" data-slug="${escapeHtml(plugin.slug)}"
              class="text-xs px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white">
        Actualizar a v${escapeHtml(plugin.version)}
      </button>`;
  }
  return '<span class="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200">Instalado &middot; actualizado</span>';
}

function pluginCard(plugin) {
  return `
    <div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 flex flex-col gap-3" data-card="${escapeHtml(plugin.slug)}">
      <div class="flex items-start justify-between gap-2">
        <div>
          <h3 class="font-medium">${escapeHtml(plugin.name)}</h3>
          <p class="text-xs text-gray-400">v${escapeHtml(plugin.version)}</p>
        </div>
      </div>
      <p class="text-sm text-gray-500 dark:text-gray-400 flex-1">${escapeHtml(plugin.description) || 'Sin descripcion.'}</p>
      <div class="flex items-center gap-2 flex-wrap" data-slot="action">
        ${actionHtmlFor(plugin)}
      </div>
    </div>`;
}

async function loadCatalog() {
  try {
    const response = await fetch('/api/v1/plugins/catalog');
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (!response.ok) {
      showFeedback('No se pudo cargar el catalogo de plugins.', true);
      return;
    }
    const data = await response.json();

    tokenStatusEl.classList.remove('hidden');
    if (data.configured) {
      tokenStatusEl.textContent = 'Token conectado';
      tokenStatusEl.className = 'text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200';
    } else {
      tokenStatusEl.textContent = 'Sin token';
      tokenStatusEl.className = 'text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400';
    }

    if (!data.configured) {
      emptyStateEl.classList.remove('hidden');
      gridEl.classList.add('hidden');
      return;
    }

    emptyStateEl.classList.add('hidden');
    gridEl.classList.remove('hidden');
    catalogBySlug = Object.fromEntries(data.plugins.map((p) => [p.slug, p]));
    gridEl.innerHTML = data.plugins.length
      ? data.plugins.map(pluginCard).join('')
      : '<p class="text-sm text-gray-500 dark:text-gray-400 col-span-full">No hay plugins publicados en el repositorio.</p>';

    const updatable = data.plugins.filter((p) => p.update_available);
    if (updatable.length) {
      updatesStatusEl.textContent = `${updatable.length} actualizacion(es) disponible(s)`;
      updatesStatusEl.classList.remove('hidden');
    } else {
      updatesStatusEl.classList.add('hidden');
    }
  } catch (err) {
    showFeedback('Error de conexion al cargar el catalogo.', true);
  } finally {
    catalogLoadingEl.classList.add('hidden');
  }
}

function renderPanelUpToDate(installedVersion) {
  panelVersionText.textContent = `Version instalada: v${installedVersion}`;
  panelUpdateAction.innerHTML = '<span class="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200">Actualizado</span>';
}

function renderPanelUpdateButton(installedVersion, remoteVersion) {
  panelVersionText.textContent = `Version instalada: v${installedVersion} · disponible: v${remoteVersion}`;
  panelUpdateAction.innerHTML = `
    <button id="panel-update-btn" type="button"
            class="text-xs px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white">
      Actualizar a v${escapeHtml(remoteVersion)}
    </button>`;
  document.getElementById('panel-update-btn').addEventListener('click', onPanelUpdateClick);
}

async function onPanelUpdateClick() {
  const info = lastPanelUpdateInfo || {};
  const confirmed = await confirmUpdate({
    title: 'Actualizar el panel principal',
    fromVersion: info.installed_version,
    toVersion: info.remote_version,
    changelog: info.changelog,
  });
  if (!confirmed) return;
  await updatePanel();
}

function renderPanelRestartButton(newVersion) {
  panelVersionText.textContent = `Version instalada: v${newVersion} (pendiente de reiniciar)`;
  panelUpdateAction.innerHTML = `
    <button id="panel-restart-btn" type="button"
            class="text-xs px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white">
      Reiniciar panel
    </button>`;
  document.getElementById('panel-restart-btn').addEventListener('click', restartPanel);
}

async function loadPanelStatus() {
  try {
    const response = await fetch('/api/system/update-check');
    if (!response.ok) return;
    const data = await response.json();
    if (!data.configured) return;

    panelUpdateCard.classList.remove('hidden');
    if (data.update_available) {
      lastPanelUpdateInfo = data;
      renderPanelUpdateButton(data.installed_version, data.remote_version);
    } else {
      lastPanelUpdateInfo = null;
      renderPanelUpToDate(data.installed_version);
    }
  } catch (err) {
    // el estado del panel no bloquea el resto de la tienda; se ignora en silencio
  }
}

async function updatePanel() {
  const button = document.getElementById('panel-update-btn');
  button.disabled = true;
  button.textContent = 'Actualizando...';
  panelUpdateLog.classList.remove('hidden');
  panelUpdateLog.textContent = 'Descargando y aplicando la actualizacion...';

  try {
    const response = await fetch('/api/system/update', { method: 'POST' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      panelUpdateLog.textContent = data.detail || 'Error desconocido al actualizar el panel.';
      showFeedback('No se pudo actualizar el panel.', true);
      await loadPanelStatus();
      return;
    }

    let log = `Actualizado de v${data.old_version} a v${data.new_version}.`;
    if (data.requirements_changed) {
      log += `\nrequirements.txt cambio: se reinstalaron dependencias.\n\n${data.pip_output}`;
    } else {
      log += '\nSin cambios en requirements.txt.';
    }
    panelUpdateLog.textContent = log;
    showFeedback(`Panel actualizado a v${data.new_version}. Reinicia para aplicar los cambios.`, false);
    renderPanelRestartButton(data.new_version);
  } catch (err) {
    panelUpdateLog.textContent = 'Error de conexion al actualizar el panel.';
    showFeedback('Error de conexion al actualizar el panel.', true);
    await loadPanelStatus();
  }
}

async function restartPanel() {
  if (!window.confirm(
    'El panel se reiniciara ahora mismo. Si no corre bajo un supervisor que lo levante '
    + 'solo (systemd con Restart=always, por ejemplo), quedara caido hasta que lo arranques a mano. ¿Continuar?'
  )) {
    return;
  }

  const button = document.getElementById('panel-restart-btn');
  button.disabled = true;
  button.textContent = 'Reiniciando...';

  try {
    await fetch('/api/system/restart', { method: 'POST' });
  } catch (err) {
    // se espera que la conexion se corte cuando el proceso se reinicia
  }
  panelUpdateLog.textContent += '\n\nReiniciando... recarga esta pagina en unos segundos.';
}

const ACTION_LABELS = {
  install: { verb: 'instalar', progress: 'Instalando...', done: 'instalado' },
  update: { verb: 'actualizar', progress: 'Actualizando...', done: 'actualizado' },
};

async function runPluginAction(action, slug, button) {
  if (action === 'update') {
    const plugin = catalogBySlug[slug] || {};
    const confirmed = await confirmUpdate({
      title: `Actualizar ${plugin.name || slug}`,
      fromVersion: plugin.installed_version,
      toVersion: plugin.version,
      changelog: plugin.changelog,
    });
    if (!confirmed) return;
  }

  const labels = ACTION_LABELS[action];
  const card = gridEl.querySelector(`[data-card="${CSS.escape(slug)}"]`);
  const actionSlot = card ? card.querySelector('[data-slot="action"]') : null;
  const originalHtml = actionSlot ? actionSlot.innerHTML : '';
  button.disabled = true;
  button.textContent = labels.progress;

  try {
    const response = await fetch(`/api/v1/plugins/${action}/${encodeURIComponent(slug)}`, { method: 'POST' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      showFeedback(`No se pudo ${labels.verb} "${slug}": ${data.detail || 'error desconocido'}`, true);
      if (actionSlot) actionSlot.innerHTML = originalHtml;
      return;
    }

    showFeedback(`Plugin "${data.plugin.name}" ${labels.done} correctamente (v${data.plugin.version}).`, false);
    if (actionSlot) {
      const openLink = data.plugin.has_ui && data.plugin.route
        ? `<a href="${escapeHtml(data.plugin.route)}" class="text-xs text-brand-600 hover:underline">Abrir</a>`
        : '';
      actionSlot.innerHTML = `
        <span class="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200">Instalado &middot; actualizado</span>
        ${openLink}`;
    }
  } catch (err) {
    showFeedback(`Error de conexion al ${labels.verb} "${slug}".`, true);
    if (actionSlot) actionSlot.innerHTML = originalHtml;
  }
}

gridEl.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action="install"], button[data-action="update"]');
  if (!button) return;
  runPluginAction(button.dataset.action, button.dataset.slug, button);
});

document.getElementById('token-btn').addEventListener('click', openTokenModal);
document.getElementById('empty-state-connect-btn').addEventListener('click', openTokenModal);
document.getElementById('token-modal-cancel').addEventListener('click', closeTokenModal);
tokenModal.addEventListener('click', (event) => {
  if (event.target === tokenModal) closeTokenModal();
});

document.getElementById('token-modal-save').addEventListener('click', async () => {
  const token = tokenInput.value.trim();
  if (!token) {
    tokenModalError.textContent = 'Introduce un token.';
    tokenModalError.classList.remove('hidden');
    return;
  }

  const saveBtn = document.getElementById('token-modal-save');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Verificando...';
  tokenModalError.classList.add('hidden');

  try {
    const response = await fetch('/api/v1/plugins/setup-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      tokenModalError.textContent = data.detail || 'No se pudo verificar el token.';
      tokenModalError.classList.remove('hidden');
      return;
    }
    closeTokenModal();
    showFeedback('Token de GitHub guardado correctamente.', false);
    await Promise.all([loadCatalog(), loadPanelStatus()]);
  } catch (err) {
    tokenModalError.textContent = 'Error de conexion al guardar el token.';
    tokenModalError.classList.remove('hidden');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Guardar';
  }
});

loadCatalog();
loadPanelStatus();
