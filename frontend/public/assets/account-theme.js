// Applies the appearance chosen in the workspace (Settings → 外觀) to the Django account pages.
// Same storage key as frontend/src/stores/theme.ts; storage can be unavailable, so fall back to the system.
(function () {
  var mode = 'system'
  try { mode = localStorage.getItem('knowledge-hub.app.theme') || 'system' } catch (error) { /* storage disabled */ }
  var dark = mode === 'dark' || (mode === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
  if (dark) document.documentElement.classList.add('hub-dark')
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
})()
