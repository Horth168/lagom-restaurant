import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useI18n } from '../i18n'

const EXIT_MS = 240

/**
 * Bottom sheet on phones, centred dialog on larger screens.
 * Slides up when opening and down when closing; Escape and tapping outside close it.
 *
 * Focus is moved into the sheet ONCE when it opens. (It used to happen on every update,
 * which took focus away from text boxes while typing and closed the phone keyboard.)
 */
export function Sheet({ open, onClose, children, label, footer }) {
  const { t } = useI18n()
  const panel = useRef(null)
  const closeRef = useRef(onClose)
  const [mounted, setMounted] = useState(open)
  const [leaving, setLeaving] = useState(false)
  // While sliding away, keep showing what was there (many callers clear their content on close)
  const lastChildren = useRef(children)
  const lastFooter = useRef(footer)
  if (open) {
    lastChildren.current = children
    lastFooter.current = footer
  }
  const body = open ? children : lastChildren.current
  const foot = open ? footer : lastFooter.current

  useEffect(() => {
    closeRef.current = onClose
  })

  // Keep the sheet on screen while it slides away
  useEffect(() => {
    if (open) {
      setMounted(true)
      setLeaving(false)
      return
    }
    if (!mounted) return
    setLeaving(true)
    const id = setTimeout(() => {
      setMounted(false)
      setLeaving(false)
    }, EXIT_MS)
    return () => clearTimeout(id)
  }, [open, mounted])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && closeRef.current?.()
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    if (!panel.current?.contains(document.activeElement)) panel.current?.focus({ preventScroll: true })
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open])

  if (!mounted) return null
  // Rendered at the end of <body>: a parent with backdrop blur would otherwise trap the fixed overlay
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={label}>
      <button
        className={`absolute inset-0 cursor-default bg-black/50 ${leaving ? 'animate-fade-out' : 'animate-fade-in'}`}
        aria-label={t('common.close')}
        onClick={() => closeRef.current?.()}
      />
      <div
        ref={panel}
        tabIndex={-1}
        className={`relative flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-[22px] border border-line/60 bg-surface text-ink shadow-[0_-10px_40px_rgba(0,0,0,0.25)] outline-none sm:max-w-lg sm:rounded-2xl ${
          leaving ? 'animate-sheet-down' : 'animate-sheet-up'
        }`}
      >
        <span className="mx-auto mt-2 block h-1 w-10 shrink-0 rounded-full bg-line sm:hidden" aria-hidden="true" />
        <button
          onClick={() => closeRef.current?.()}
          className="press absolute top-3 right-3 z-10 grid size-9 place-items-center rounded-full bg-surface-2 text-ink"
          aria-label={t('common.close')}
        >
          <X size={18} />
        </button>
        <div className="flex-1 overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)]">{body}</div>
        {foot && <div className="border-t border-line bg-surface p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">{foot}</div>}
      </div>
    </div>,
    document.body,
  )
}
