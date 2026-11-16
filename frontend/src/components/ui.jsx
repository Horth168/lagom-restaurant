/* Small shared UI kit for staff screens (admin + POS). */
import { createContext, useCallback, useContext, useState } from 'react'
import { CheckCircle2, X, XCircle } from 'lucide-react'
import { useI18n } from '../i18n'

export function Card({ title, action, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-line bg-surface ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

const BTN = {
  primary: 'bg-brand text-on-brand hover:opacity-90',
  secondary: 'border border-line bg-surface text-ink hover:bg-surface-2',
  danger: 'bg-danger text-white hover:opacity-90',
  ghost: 'text-ink hover:bg-surface-2',
}

export function Button({ variant = 'secondary', size = 'md', className = '', ...props }) {
  const sz = size === 'sm' ? 'h-9 px-3 text-sm' : size === 'lg' ? 'h-12 px-5 text-[15px]' : 'h-10 px-4 text-sm'
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${sz} ${BTN[variant]} ${className}`}
    />
  )
}

const TONES = {
  neutral: 'bg-surface-2 text-ink',
  // tinted from theme colours, so they work in light and dark mode
  good: 'bg-series-1/15 text-series-1',
  warn: 'bg-series-2/15 text-series-2',
  bad: 'bg-danger/15 text-danger',
  info: 'bg-[#4a78a8]/15 text-[#4a78a8]',
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]}`}>{children}</span>
}

export const STATUS_TONE = {
  PENDING_PAYMENT: 'warn', PAID: 'info', PREPARING: 'info', READY: 'good', SERVED: 'neutral',
  CANCELLED: 'bad', EXPIRED: 'neutral',
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="text-sm font-medium">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

/** Input style without a width (combine with w-24, w-40…) */
export const inputBase =
  'h-10 rounded-lg border border-line bg-bg px-3 text-[15px] outline-none focus:border-accent disabled:opacity-60'
export const inputCls = `${inputBase} w-full`

export function Skeleton({ className = '' }) {
  return <div className={`skeleton rounded-lg ${className}`} />
}

// ---------------------------------------------------------------- toasts
const ToastCtx = createContext(() => {})

export function ToastProvider({ children }) {
  const { t } = useI18n()
  const [items, setItems] = useState([])
  const push = useCallback((message, tone = 'good') => {
    const id = Math.random().toString(36).slice(2)
    setItems((xs) => [...xs, { id, message, tone }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex flex-col gap-2" aria-live="polite">
        {items.map((x) => (
          <div key={x.id} className="pointer-events-auto flex items-center gap-3 rounded-xl bg-ink px-4 py-3 text-sm text-bg shadow-xl animate-fade-in">
            {x.tone === 'bad' ? <XCircle size={18} className="text-[#ff9b8a]" /> : <CheckCircle2 size={18} className="text-[#9fd49a]" />}
            {x.message}
            <button onClick={() => setItems((xs) => xs.filter((y) => y.id !== x.id))} aria-label={t('common.close')} className="opacity-60">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  return useContext(ToastCtx)
}

// ---------------------------------------------------------------- money input
/** "4.50" -> 450 ; "" -> null */
export function parseUsd(text) {
  const t = String(text ?? '').replace(/[$,\s]/g, '')
  if (!/^\d+(\.\d{0,2})?$/.test(t)) return null
  return Math.round(Number(t) * 100)
}

export function centsToInput(cents) {
  return (cents / 100).toFixed(2)
}
