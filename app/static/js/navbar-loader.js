function navbarEscapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
}

function pluginMenuItem(plugin) {
  const icon = plugin.icon ? `<i class="fa-solid ${navbarEscapeHtml(plugin.icon)} w-4 text-center text-gray-400"></i>` : '';
  return `
    <a href="${navbarEscapeHtml(plugin.route)}" class="flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800">
      ${icon}
      ${navbarEscapeHtml(plugin.title)}
    </a>`;
}

const PLUGINS_MENU_LINK = `
  <a href="/plugins/menu" class="flex items-center gap-2 px-3 py-2 text-sm font-medium text-brand-600 dark:text-brand-400 hover:bg-gray-100 dark:hover:bg-gray-800 border-b border-gray-200 dark:border-gray-800">
    <i class="fa-solid fa-grip w-4 text-center"></i>
    Ver todos los plugins
  </a>`;

async function loadPluginsMenu() {
  const pluginsMenu = document.getElementById('plugins-menu');
  try {
    const response = await fetch('/api/v1/plugins/');
    if (!response.ok) {
      pluginsMenu.innerHTML = PLUGINS_MENU_LINK + '<p class="px-3 py-2 text-sm text-gray-400">No se pudo cargar los plugins</p>';
      return;
    }
    const pluginsList = await response.json();
    const withUi = pluginsList.filter((plugin) => plugin.has_ui && plugin.route);
    pluginsMenu.innerHTML = PLUGINS_MENU_LINK + (withUi.length
      ? withUi.map(pluginMenuItem).join('')
      : '<p class="px-3 py-2 text-sm text-gray-400">Sin plugins con interfaz</p>');
  } catch (err) {
    pluginsMenu.innerHTML = PLUGINS_MENU_LINK + '<p class="px-3 py-2 text-sm text-gray-400">No se pudo cargar los plugins</p>';
  }
}

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
    // la tienda no es critica para el navbar; se ignora en silencio
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

async function checkCoreUpdates() {
  const btn = document.getElementById('core-updates-btn');
  const label = document.getElementById('core-updates-label');
  const badge = document.getElementById('core-updates-badge');

  function showNoPlugin() {
    label.textContent = 'Sin plugin gestor';
    badge.classList.add('hidden');
    btn.removeAttribute('href');
    btn.classList.add('opacity-60', 'cursor-default');
  }

  let installed = false;
  try {
    const pluginsResponse = await fetch('/api/v1/plugins/');
    const plugins = pluginsResponse.ok ? await pluginsResponse.json() : [];
    installed = plugins.some((plugin) => plugin.slug === 'core_updater');
  } catch (err) {
    return; // sin respuesta de /api/v1/plugins/: se deja el boton como estaba, se reintenta en el siguiente ciclo
  }
  if (!installed) {
    showNoPlugin();
    return;
  }
  try {
    const response = await fetch('/api/v1/plugins/core_updater/updates-summary');
    if (!response.ok) throw new Error('sin respuesta');
    const data = await response.json();
    const count = data.total_behind || 0;
    btn.setAttribute('href', '/api/v1/plugins/core_updater/view');
    btn.classList.remove('opacity-60', 'cursor-default');
    if (count > 0) {
      label.textContent = 'Actualizaciones disponibles';
      badge.textContent = count;
      badge.classList.remove('hidden');
    } else {
      label.textContent = 'Núcleo actualizado';
      badge.classList.add('hidden');
    }
  } catch (err) {
    // el plugin esta instalado pero el resumen fallo momentaneamente: se deja el
    // boton como estaba, se reintenta en el siguiente ciclo
  }
}

function bindNavbarActions() {
  document.getElementById('logout-btn').addEventListener('click', async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  });

  document.getElementById('restart-panel-btn').addEventListener('click', async () => {
    if (!window.confirm('¿Reiniciar el panel? Se cerrará la sesión de todos los usuarios durante unos segundos.')) {
      return;
    }
    try {
      await fetch('/api/system/restart', { method: 'POST' });
    } catch (err) {
      // El panel se reinicia y corta la conexion; un fallo de fetch aqui es el resultado esperado.
    }
  });

  const pluginsMenuBtn = document.getElementById('plugins-menu-btn');
  const pluginsMenu = document.getElementById('plugins-menu');
  pluginsMenuBtn.addEventListener('click', (event) => {
    event.stopPropagation();
    pluginsMenu.classList.toggle('hidden');
  });
  document.addEventListener('click', () => pluginsMenu.classList.add('hidden'));
}

async function loadNavbar(mountSelector) {
  const mount = document.querySelector(mountSelector);
  if (!mount) return;
  try {
    const response = await fetch('/api/navbar');
    if (!response.ok) return;
    mount.innerHTML = await response.text();
  } catch (err) {
    return;
  }

  bindNavbarActions();
  if (window.initThemeToggle) window.initThemeToggle();
  loadPluginsMenu();
  checkUpdates();
  checkCoreUpdates();
  setInterval(checkCoreUpdates, 60000);
}

document.addEventListener('DOMContentLoaded', () => loadNavbar('#navbar-mount'));
