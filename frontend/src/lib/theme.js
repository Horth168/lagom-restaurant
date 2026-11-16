// Light / dark mode. Default follows the phone's setting; the toggle remembers the choice.
export function currentTheme() {
  const forced = document.documentElement.dataset.theme
  if (forced === 'light' || forced === 'dark') return forced
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = next
  try {
    localStorage.setItem('lagom.theme', next)
  } catch {
    /* ignore */
  }
  return next
}
