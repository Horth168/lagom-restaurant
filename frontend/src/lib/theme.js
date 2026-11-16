// Light / dark mode. Default follows the phone's setting; the toggle remembers the choice.
// Switching shows a circle that grows from the button (where the browser supports it),
// otherwise a soft colour fade. People who turned off motion on their phone get an instant switch.
export function currentTheme() {
  const forced = document.documentElement.dataset.theme
  if (forced === 'light' || forced === 'dark') return forced
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function save(next) {
  document.documentElement.dataset.theme = next
  try {
    localStorage.setItem('lagom.theme', next)
  } catch {
    /* ignore */
  }
}

/** @param {MouseEvent} [event] the click, so the circle starts at the button */
export function toggleTheme(event) {
  const next = currentTheme() === 'dark' ? 'light' : 'dark'
  const root = document.documentElement
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  if (reduced) {
    save(next)
    return next
  }
  if (!document.startViewTransition) {
    root.classList.add('theme-fade')
    save(next)
    setTimeout(() => root.classList.remove('theme-fade'), 400)
    return next
  }
  const rect = event?.currentTarget?.getBoundingClientRect?.()
  const x = rect ? rect.left + rect.width / 2 : window.innerWidth - 40
  const y = rect ? rect.top + rect.height / 2 : 40
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
  const transition = document.startViewTransition(() => save(next))
  transition.ready
    .then(() => {
      root.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 550, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', pseudoElement: '::view-transition-new(root)' },
      )
    })
    .catch(() => {})
  return next
}
