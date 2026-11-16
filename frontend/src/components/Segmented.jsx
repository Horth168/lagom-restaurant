/* One-row segmented control (e.g. Today · Yesterday · Last 7 days …).
 * Never wraps: on small phones it slides sideways with soft faded edges, and the
 * chosen option is scrolled into view. The selected option sits raised in the track. */
import { useEffect, useRef, useState } from 'react'

export function Segmented({ options, value, onChange, label, className = '', size = 'md' }) {
  const track = useRef(null)
  const [edges, setEdges] = useState({ left: false, right: false })

  const measure = () => {
    const el = track.current
    if (!el) return
    setEdges({ left: el.scrollLeft > 2, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 2 })
  }

  useEffect(() => {
    const el = track.current
    if (!el) return
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Keep the chosen option visible (e.g. "Custom" at the end on a narrow phone)
  useEffect(() => {
    const t = track.current
    const el = t?.querySelector('[aria-checked="true"]')
    if (!t || !el) return
    // slide only the control sideways (never scroll the page)
    const left = el.offsetLeft - 24
    const right = el.offsetLeft + el.offsetWidth + 24 - t.clientWidth
    if (left < t.scrollLeft) t.scrollTo({ left, behavior: 'smooth' })
    else if (right > t.scrollLeft) t.scrollTo({ left: right, behavior: 'smooth' })
  }, [value])

  const mask = edges.left && edges.right
    ? 'linear-gradient(to right, transparent, #000 20px, #000 calc(100% - 20px), transparent)'
    : edges.left ? 'linear-gradient(to right, transparent, #000 20px)'
      : edges.right ? 'linear-gradient(to right, #000 calc(100% - 20px), transparent)' : undefined
  const h = size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-9 px-3.5 text-sm'

  return (
    <div className={`max-w-full ${className}`}>
      <div
        ref={track}
        role="radiogroup"
        aria-label={label}
        onScroll={measure}
        className="no-scrollbar flex w-full gap-0.5 overflow-x-auto rounded-xl bg-surface-2 p-1 sm:w-auto"
        style={mask ? { maskImage: mask, WebkitMaskImage: mask } : undefined}
      >
        {options.map((o) => {
          const on = o.value === value
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(o.value)}
              className={`${h} shrink-0 whitespace-nowrap rounded-lg font-medium transition-[background-color,color,box-shadow] duration-200 motion-reduce:transition-none ${
                on ? 'bg-surface text-ink shadow-[0_1px_2px_rgba(0,0,0,0.12),0_0_0_1px_var(--line)]' : 'text-muted hover:text-ink'
              }`}
            >
              {o.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
