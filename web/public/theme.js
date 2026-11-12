// Runs before first paint so dark mode does not flash. Kept in sync with src/lib/theme.ts.
;(function () {
  var stored = null
  try {
    stored = localStorage.getItem('theme')
  } catch {}
  var dark =
    stored === 'dark' ||
    (stored !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
})()
