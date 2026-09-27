function initThemeToggle() {
  const toggle = document.getElementById('theme-toggle');
  if (!toggle || toggle.dataset.themeBound) return;
  toggle.dataset.themeBound = '1';
  toggle.addEventListener('click', () => {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.theme = isDark ? 'dark' : 'light';
  });
}
window.initThemeToggle = initThemeToggle;
initThemeToggle();
