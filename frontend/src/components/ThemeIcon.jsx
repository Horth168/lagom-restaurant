/* Sun ↔ moon that turns and fades into each other when the theme changes. */
import { Moon, Sun } from 'lucide-react'

export function ThemeIcon({ theme, size = 18 }) {
  const dark = theme === 'dark'
  const base = 'absolute inset-0 m-auto transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none'
  return (
    <span className="relative inline-block" style={{ width: size, height: size }} aria-hidden="true">
      {/* In dark mode the button offers the sun (switch to light), and the other way round */}
      <Sun size={size} className={`${base} ${dark ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-50 opacity-0'}`} />
      <Moon size={size} className={`${base} ${dark ? 'rotate-90 scale-50 opacity-0' : 'rotate-0 scale-100 opacity-100'}`} />
    </span>
  )
}
