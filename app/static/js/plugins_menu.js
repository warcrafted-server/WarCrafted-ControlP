function menuEscapeHtml(text) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, (char) => map[char]);
}

function pluginMenuCard(plugin) {
  const icon = plugin.icon ? plugin.icon : 'fa-puzzle-piece';
  return `
    <a href="${menuEscapeHtml(plugin.route)}"
       class="group flex flex-col gap-3 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 hover:border-brand-400 hover:shadow-md transition-all">
      <div class="w-14 h-14 rounded-xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center">
        <i class="fa-solid ${menuEscapeHtml(icon)} text-2xl text-brand-600 dark:text-brand-400"></i>
      </div>
      <div>
        <h2 class="text-base font-semibold group-hover:text-brand-600 dark:group-hover:text-brand-400">${menuEscapeHtml(plugin.title)}</h2>
        <p class="text-xs text-gray-400 mt-0.5">v${menuEscapeHtml(plugin.version)}</p>
      </div>
      <p class="text-sm text-gray-500 dark:text-gray-400 flex-1">${menuEscapeHtml(plugin.description || 'Sin descripción.')}</p>
      <span class="text-sm text-brand-600 dark:text-brand-400 font-medium">
        Abrir <i class="fa-solid fa-arrow-right text-xs"></i>
      </span>
    </a>`;
}

async function loadPluginsMenu() {
  const loading = document.getElementById('menu-loading');
  const empty = document.getElementById('menu-empty');
  const grid = document.getElementById('menu-grid');
  try {
    const response = await fetch('/api/v1/plugins/');
    const plugins = response.ok ? await response.json() : [];
    const withUi = plugins.filter((plugin) => plugin.has_ui && plugin.route);
    loading.classList.add('hidden');
    if (!withUi.length) {
      empty.classList.remove('hidden');
      return;
    }
    grid.innerHTML = withUi.map(pluginMenuCard).join('');
    grid.classList.remove('hidden');
  } catch (err) {
    loading.classList.add('hidden');
    empty.classList.remove('hidden');
  }
}

loadPluginsMenu();
