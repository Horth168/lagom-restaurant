import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Banknote, Check, ChevronRight, Clock, Download, ShieldCheck } from 'lucide-react'
import { KhqrCard } from '../../components/KhqrCard'
import { KhqrLogo } from '../../components/KhqrLogo'
import { useI18n } from '../../i18n'
import { api, ApiError } from '../../lib/api'
import { formatKHR, formatUSD } from '../../lib/money'
import { useLiveChannel } from '../../lib/realtime'
import { useCustomer } from './CustomerContext'
import { Header } from './Header'

// Live updates arrive instantly over the WebSocket; these checks are only a safety net
const POLL_PAYING_MS = 5000
const POLL_TRACKING_MS = 15000

export function OrderPage() {
  const { publicId } = useParams()
  const { t } = useI18n()
  const { headers, session } = useCustomer()
  const [order, setOrder] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setOrder(await api(`/api/public/orders/${publicId}`, { headers }))
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? 'notfound' : 'offline')
    }
  }, [publicId, headers])

  useEffect(() => {
    load()
  }, [load])

  // Instant updates: payment confirmed, preparing, ready, served
  useLiveChannel('/api/ws/customer', { session: session?.session_token }, (msg) => {
    if (msg.type === 'reconnected' || msg.order === publicId) load()
  }, !!session)

  // Keep checking: while paying (the server also double-checks with ABA) and while the kitchen works
  const active = order && !['SERVED', 'CANCELLED', 'EXPIRED'].includes(order.status)
  useEffect(() => {
    if (!active) return
    const ms = order.status === 'PENDING_PAYMENT' ? POLL_PAYING_MS : POLL_TRACKING_MS
    const id = setInterval(() => document.visibilityState === 'visible' && load(), ms)
    return () => clearInterval(id)
  }, [active, order?.status, load])

  if (error === 'notfound') {
    return (
      <Shell title={t('orders.title')} back="../orders">
        <p className="py-20 text-center text-muted">{t('entry.invalid')}</p>
      </Shell>
    )
  }
  if (!order) {
    return (
      <Shell title={t('pay.title')} back="..">
        <div className="space-y-3 pt-6">
          <div className="skeleton h-24 rounded-2xl" />
          <div className="skeleton h-64 rounded-2xl" />
        </div>
      </Shell>
    )
  }
  if (order.status === 'PENDING_PAYMENT') return <PaymentView order={order} onChange={setOrder} reload={load} />
  if (order.status === 'EXPIRED') {
    return (
      <Shell title={t('pay.order', { n: order.number })} back="..">
        <div className="flex flex-col items-center gap-5 py-16 text-center">
          <Clock size={40} strokeWidth={1.25} className="text-sand" />
          <p className="max-w-xs text-muted">{t('pay.expired')}</p>
          <Link to=".." className="rounded-full bg-brand px-6 py-3 text-sm font-medium text-on-brand">{t('pay.orderAgain')}</Link>
        </div>
      </Shell>
    )
  }
  return <TrackingView order={order} />
}

function Shell({ title, back, children }) {
  return (
    <div className="min-h-dvh pb-12">
      <Header title={title} backTo={back} />
      <main className="mx-auto max-w-2xl px-4">{children}</main>
    </div>
  )
}

// ------------------------------------------------------------------ payment
function PaymentView({ order, onChange, reload }) {
  const { t } = useI18n()
  const { headers } = useCustomer()
  const [options, setOptions] = useState(null)
  const [currency, setCurrency] = useState('USD')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState(null)
  const [choosing, setChoosing] = useState(!order.payment)

  useEffect(() => {
    api('/api/public/payment-options').then(setOptions).catch(() => setOptions({ khqr_available: false, cash_available: true }))
  }, [])

  async function start(method) {
    setBusy(true)
    setProblem(null)
    try {
      const updated = await api(`/api/public/orders/${order.public_id}/pay`, { method: 'POST', headers, body: { method, currency } })
      onChange(updated)
      setChoosing(false)
    } catch (e) {
      setProblem(e instanceof ApiError && e.status ? e.message : t('entry.offline'))
      if (e.status === 409 || e.status === 410) reload()
    } finally {
      setBusy(false)
    }
  }

  const total = currency === 'KHR' ? formatKHR(order.total_khr) : formatUSD(order.total_usd_cents)
  const methods = [
    { id: 'khqr', available: options?.khqr_available, hint: t('pay.khqr.hint') },
    { id: 'cash', available: options?.cash_available, hint: t('pay.cash.hint') },
  ]

  return (
    <Shell title={t('pay.title')} back="..">
      <div className="pt-5">
        <div className="flex items-baseline justify-between">
          <h1 className="font-display text-3xl">{t('pay.order', { n: order.number })}</h1>
          <span className="text-sm text-muted">{order.table}</span>
        </div>
        <p className="mt-1 text-sm text-muted">
          {order.items.reduce((n, i) => n + i.quantity, 0)} · {formatUSD(order.total_usd_cents)} · {formatKHR(order.total_khr)}
        </p>
      </div>

      {options?.test_mode && (
        <p className="mt-4 rounded-lg border border-dashed border-accent px-3 py-2 text-center text-xs font-semibold tracking-wide text-accent">
          {t('pay.testMode')}
        </p>
      )}

      {choosing || !order.payment ? (
        <section className="mt-6">
          {options?.currencies?.length > 1 && (
            <div className="mb-5">
              <span className="text-sm font-medium">{t('pay.currency')}</span>
              <div className="mt-2 grid grid-cols-2 gap-2" role="radiogroup">
                {options.currencies.map((c) => (
                  <button
                    key={c}
                    role="radio"
                    aria-checked={currency === c}
                    onClick={() => setCurrency(c)}
                    className={`h-12 rounded-xl border text-[15px] font-medium tabular-nums ${currency === c ? 'border-brand bg-brand text-on-brand' : 'border-line bg-surface'}`}
                  >
                    {c === 'KHR' ? formatKHR(order.total_khr) : formatUSD(order.total_usd_cents)}
                  </button>
                ))}
              </div>
            </div>
          )}
          <h2 className="text-sm font-medium">{t('pay.choose')}</h2>
          <ul className="mt-2 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
            {methods.map((m) => (
              <li key={m.id}>
                <button
                  onClick={() => start(m.id)}
                  disabled={busy || !options || !m.available}
                  className="flex w-full items-center gap-4 px-4 py-4 text-left disabled:opacity-40"
                >
                  {m.id === 'khqr' ? (
                    <span className="grid h-10 w-14 shrink-0 place-items-center rounded-md border border-line bg-white">
                      <KhqrLogo height={13} />
                    </span>
                  ) : (
                    <span className="grid h-10 w-14 shrink-0 place-items-center rounded-md bg-surface-2 text-ink">
                      <Banknote size={20} strokeWidth={1.75} />
                    </span>
                  )}
                  <span className="flex-1">
                    <span className="block font-medium">{t(`pay.${m.id}`)}</span>
                    <span className="block text-xs text-muted">{m.hint}</span>
                  </span>
                  <span className="text-sm font-semibold tabular-nums">{total}</span>
                  <ChevronRight size={18} className="text-muted" />
                </button>
              </li>
            ))}
          </ul>
          {options && !options.khqr_available && <p className="mt-3 text-center text-xs text-muted">{t('pay.unavailable', { n: order.number })}</p>}
          {busy && <p className="mt-4 text-center text-sm text-muted">{t('pay.starting')}</p>}
          {problem && <p className="mt-4 text-center text-sm text-danger" role="alert">{problem}</p>}
          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted">
            <ShieldCheck size={14} /> {t('pay.secure')}
          </p>
        </section>
      ) : order.payment.method === 'cash' ? (
        <CashWaiting order={order} onChooseAnother={() => setChoosing(true)} />
      ) : (
        <KhqrPayment order={order} testMode={options?.test_mode} onChooseAnother={() => setChoosing(true)} reload={reload} />
      )}
    </Shell>
  )
}

function WaitingDot({ label }) {
  return (
    <div className="flex items-center gap-2 text-sm" aria-live="polite">
      <span className="relative flex size-2.5">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-60" />
        <span className="relative inline-flex size-2.5 rounded-full bg-accent" />
      </span>
      {label}
    </div>
  )
}

function CashWaiting({ order, onChooseAnother }) {
  const { t } = useI18n()
  const p = order.payment
  const amount = p.currency === 'KHR' ? formatKHR(p.amount_minor) : formatUSD(p.amount_minor)
  return (
    <section className="mt-6 flex flex-col items-center text-center">
      <div className="w-full rounded-2xl border border-line bg-surface p-6">
        <Banknote size={36} strokeWidth={1.25} className="mx-auto text-accent" />
        <h2 className="mt-3 font-display text-2xl">{t('pay.cashTitle')}</h2>
        <p className="mt-4 font-display text-6xl text-accent">#{order.number}</p>
        <p className="mt-2 text-2xl font-semibold tabular-nums">{amount}</p>
        <p className="mx-auto mt-4 max-w-xs text-sm text-muted">{t('pay.cashBody', { n: order.number })}</p>
      </div>
      <div className="mt-6"><WaitingDot label={t('pay.waiting')} /></div>
      <button onClick={onChooseAnother} className="mt-6 text-sm font-medium text-accent underline-offset-4 hover:underline">
        {t('pay.change')}
      </button>
    </section>
  )
}

function KhqrPayment({ order, testMode, onChooseAnother, reload }) {
  const { t } = useI18n()
  const { headers } = useCustomer()
  const p = order.payment
  const [qrSrc, setQrSrc] = useState('')
  const remaining = useCountdown(p.expires_at)
  const [simulating, setSimulating] = useState(false)


  async function simulate() {
    setSimulating(true)
    try {
      await api('/api/dev/khqr/simulate-payment', { method: 'POST', headers, body: { public_id: order.public_id } })
      await reload()
    } finally {
      setSimulating(false)
    }
  }

  return (
    <section className="mt-6 flex flex-col items-center">
      <KhqrCard qrString={p.qr_string} amountMinor={p.amount_minor} currency={p.currency} onQr={setQrSrc} />
      <p className="mt-5 max-w-xs text-center text-sm text-muted">{t('pay.scan')}</p>
      {qrSrc && (
        <a
          href={qrSrc}
          download={`LAGOM-order-${order.number}-KHQR.png`}
          className="mt-4 flex h-12 w-full max-w-[300px] items-center justify-center gap-2 rounded-full bg-brand font-semibold text-on-brand"
        >
          <Download size={18} /> {t('pay.saveQr')}
        </a>
      )}
      <p className="mt-2 max-w-xs text-center text-xs text-muted">{t('pay.samePhone')}</p>

      <div className="mt-6"><WaitingDot label={t('pay.waiting')} /></div>
      {remaining && <p className="mt-1 text-xs text-muted tabular-nums">{t('pay.expiresIn', { time: remaining })}</p>}
      <p className="mt-2 max-w-xs text-center text-xs text-muted">{t('pay.auto')}</p>

      {testMode && (
        <button
          onClick={simulate}
          disabled={simulating}
          className="mt-6 rounded-full border border-dashed border-accent px-5 py-2.5 text-sm font-medium text-accent disabled:opacity-50"
        >
          {t('pay.simulate')}
        </button>
      )}
      <button onClick={onChooseAnother} className="mt-6 text-sm font-medium text-accent underline-offset-4 hover:underline">
        {t('pay.change')}
      </button>
    </section>
  )
}

function useCountdown(isoTime) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  if (!isoTime) return null
  const ms = Math.max(0, new Date(isoTime).getTime() - now)
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  return `${m}:${String(s).padStart(2, '0')}`
}

// ------------------------------------------------------------------ tracking
const STEPS = ['PAID', 'RECEIVED', 'PREPARING', 'READY', 'SERVED']

function stepIndex(order) {
  if (order.status === 'SERVED') return 4
  if (order.status === 'READY') return 3
  if (order.status === 'PREPARING') return 2
  if (order.accepted_at) return 1
  return 0
}

function TrackingView({ order }) {
  const { t, pick } = useI18n()
  const current = stepIndex(order)
  const cancelled = order.status === 'CANCELLED'
  const paid = order.payment
  const paidAmount = paid ? (paid.currency === 'KHR' ? formatKHR(paid.amount_minor) : formatUSD(paid.amount_minor)) : formatUSD(order.total_usd_cents)

  return (
    <Shell title={t('track.title', { n: order.number })} back="..">
      <section className="pt-6 text-center">
        <div className="mx-auto grid size-16 place-items-center rounded-full bg-brand text-on-brand">
          <Check size={30} strokeWidth={2} />
        </div>
        <h1 className="mt-4 font-display text-[28px] leading-tight">
          {cancelled ? t('track.cancelled') : order.status === 'READY' ? t('track.ready') : order.status === 'SERVED' ? t('track.served') : t('track.thanks')}
        </h1>
        <p className="mt-2 font-display text-6xl tracking-tight text-accent">#{order.number}</p>
        <p className="mt-1 text-sm text-muted">{order.channel === 'TELEGRAM' ? t('track.pickup') : order.table}</p>
        {!cancelled && current < 3 && (
          <p className="mt-3 inline-flex items-center gap-1.5 text-sm text-muted">
            <Clock size={14} /> {t('track.estimate', { n: order.estimated_ready_minutes })}
          </p>
        )}
      </section>

      {!cancelled && (
        <ol className="mx-auto mt-8 max-w-sm" aria-label={t('track.progress')}>
          {STEPS.map((s, i) => {
            const done = i <= current
            return (
              <li key={s} className="relative flex gap-4 pb-6 last:pb-0">
                {i < STEPS.length - 1 && (
                  <span className={`absolute left-[11px] top-6 h-full w-0.5 ${i < current ? 'bg-brand' : 'bg-line'}`} aria-hidden="true" />
                )}
                <span className={`relative z-10 grid size-6 shrink-0 place-items-center rounded-full border-2 ${done ? 'border-brand bg-brand text-on-brand' : 'border-line bg-bg'}`}>
                  {done && <Check size={13} strokeWidth={3} />}
                </span>
                <span className={`pt-0.5 ${i === current ? 'font-semibold' : done ? '' : 'text-muted'}`} aria-current={i === current ? 'step' : undefined}>
                  {t(`track.step.${s}`)}
                </span>
              </li>
            )
          })}
        </ol>
      )}

      <section className="mt-8 rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-sm font-medium text-muted">{t('track.items')}</h2>
        <ul className="mt-2 divide-y divide-line">
          {order.items.map((i, idx) => (
            <li key={idx} className="flex justify-between gap-3 py-3">
              <span>
                <span className="font-medium">{i.quantity} × {pick(i.name)}</span>
                {i.options.length > 0 && <span className="block text-sm text-muted">{i.options.map(pick).join(' · ')}</span>}
                {i.special_instructions && <span className="block text-sm italic text-muted">“{i.special_instructions}”</span>}
              </span>
              <span className="shrink-0 tabular-nums">{formatUSD(i.line_total_usd_cents)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex justify-between border-t border-line pt-3 font-semibold">
          <span>{t('track.paid')}</span>
          <span className="tabular-nums">{paidAmount}</span>
        </div>
        {paid && (
          <div className="mt-1 flex justify-between text-sm text-muted">
            <span>{t('track.reference')}</span>
            <span className="font-mono">{paid.reference}</span>
          </div>
        )}
      </section>

      <p className="mt-4 text-center text-xs text-muted">{t('track.live')}</p>
      <div className="mt-6 text-center">
        <Link to=".." className="text-sm font-medium text-accent">{t('track.newOrder')}</Link>
      </div>
    </Shell>
  )
}
