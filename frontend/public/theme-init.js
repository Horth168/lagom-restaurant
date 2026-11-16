// Apply the saved theme before the page paints (avoids a white flash in dark mode).
// A separate file (not inline) so the Content-Security-Policy can forbid inline scripts.
try {
  const t = localStorage.getItem('lagom.theme')
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
} catch {
  /* storage blocked */
}
