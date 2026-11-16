import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useI18n } from '../i18n'

/** Bottom sheet on phones, centred dialog on larger screens. Closes on Escape and backdrop tap. */
export function Sheet({ open, onClose, children, label, footer }) {
  const { t } = useI18n()
  const panel = useRef(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    panel.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onClose])

  if (!open) return null
  // Rendered at the end of <body>: a parent with backdrop blur would otherwise trap the fixed overlay
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" role="dialog" aria-modal="true" aria-label={label}>
      <button className="absolute inset-0 bg-black/45 animate-fade-in cursor-default" aria-label={t('common.close')} onClick={onClose} />
      <div
        ref={panel}
        tabIndex={-1}
        className="relative w-full sm:max-w-lg max-h-[92dvh] flex flex-col bg-surface text-ink rounded-t-2xl sm:rounded-2xl shadow-2xl animate-sheet-up outline-none overflow-hidden"
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 z-10 grid place-items-center size-9 rounded-full bg-surface/90 text-ink shadow-sm backdrop-blur"
          aria-label={t('common.close')}
        >
          <X size={18} />
        </button>
        <div className="overflow-y-auto overscroll-contain flex-1">{children}</div>
        {footer && <div className="border-t border-line bg-surface p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}
