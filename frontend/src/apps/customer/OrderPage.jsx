import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import QRCode from 'qrcode'
import { Check, ChevronRight, Clock, ShieldCheck, Smartphone } from 'lucide-react'
import { useI18n } from '../../i18n'
import { api, ApiError } from '../../lib/api'
import { formatKHR, formatUSD } from '../../lib/money'
import { useCustomer } from './CustomerContext'
import { Header } from './Header'

const POLL_PAYING_MS = 3000
const POLL_TRACKING_MS = 5000

export function OrderPage() {
  const { publicId } = useParams()
  const { t } = useI18n()
  const { headers } = useCustomer()
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
    api('/api/public/payment-options').then(setOptions).catch(() => setOptions({ online_payment_available: false }))
  }, [])

  async function start(paymentOption) {
    setBusy(true)
    setProblem(null)
    try {
      const updated = await api(`/api/public/orders/${order.public_id}/pay`, {
        method: 'POST',
        headers,
        body: { payment_option: paymentOption, currency },
      })
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
      {options?.sandbox && (
        <p className="mt-4 rounded-lg border border-dashed border-accent px-3 py-2 text-center text-xs text-accent">{t('pay.sandbox')}</p>
      )}

      {options && !options.online_payment_available ? (
        <p className="mt-8 rounded-2xl bg-surface-2 p-5 text-center">{t('pay.unavailable', { n: order.number })}</p>
      ) : choosing || !order.payment ? (
        <section className="mt-6">
          {options && options.currencies?.length > 1 && (
            <div className="mb-5">
              <span className="text-sm font-medium">{t('pay.currency')}</span>
              <div className="mt-2 grid grid-cols-2 gap-2" role="radiogroup">
                {options.currencies.map((c) => (
                  <button
                    key={c}
                    role="radio"
                    aria-checked={currency === c}
                    onClick={() => setCurrency(c)}
                    className={`h-12 rounded-xl border text-[15px] font-medium ${currency === c ? 'border-brand bg-brand text-on-brand' : 'border-line bg-surface'}`}
                  >
                    {c === 'KHR' ? `៛ ${formatKHR(order.total_khr)}` : `$ ${formatUSD(order.total_usd_cents).slice(1)}`}
                  </button>
                ))}
              </div>
            </div>
          )}
          <h2 className="text-sm font-medium">{t('pay.choose')}</h2>
          <ul className="mt-2 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
            {(options?.options ?? []).map((o) => {
              const allowed = o.currencies.includes(currency)
              return (
                <li key={o.id}>
                  <button
                    onClick={() => start(o.id)}
                    disabled={busy || !allowed}
                    className="flex w-full items-center gap-4 px-4 py-4 text-left disabled:opacity-40"
                  >
                    <PayMark id={o.id} />
                    <span className="flex-1">
                      <span className="block font-medium">{t(`pay.${o.id}`)}</span>
                      <span className="block text-xs text-muted">
                        {o.id === 'abapay_khqr' ? t('pay.abapay_khqr.hint') : t('pay.usdOnly')}
                      </span>
                    </span>
                    <span className="text-sm font-semibold tabular-nums">{allowed ? total : ''}</span>
                    <ChevronRight size={18} className="text-muted" />
                  </button>
                </li>
              )
            })}
          </ul>
          {busy && <p className="mt-4 text-center text-sm text-muted">{t('pay.starting')}</p>}
          {problem && <p className="mt-4 text-center text-sm text-danger" role="alert">{problem}</p>}
          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted">
            <ShieldCheck size={14} /> {t('pay.secure')}
          </p>
        </section>
      ) : (
        <QrPayment order={order} testMode={options?.test_mode} onChooseAnother={() => setChoosing(true)} reload={reload} />
      )}
    </Shell>
  )
}

function PayMark({ id }) {
  const style = {
    abapay_khqr: 'bg-[#E1232E] text-white',
    wechat: 'bg-[#07C160] text-white',
    alipay: 'bg-[#1677FF] text-white',
  }[id]
  const label = { abapay_khqr: 'KHQR', wechat: 'WeChat', alipay: 'Alipay' }[id]
  return <span className={`grid h-9 w-14 shrink-0 place-items-center rounded-md text-[10px] font-bold ${style}`}>{label}</span>
}

function QrPayment({ order, testMode, onChooseAnother, reload }) {
  const { t } = useI18n()
  const p = order.payment
  const [qrSrc, setQrSrc] = useState('')
  const remaining = useCountdown(p.expires_at)
  const [simulating, setSimulating] = useState(false)
  const isMobile = typeof navigator !== 'undefined' && /Android|iPhone|iPad/i.test(navigator.userAgent)

  useEffect(() => {
    // Drawn on the phone from PayWay's QR text (lighter than downloading PayWay's large QR image)
    QRCode.toDataURL(p.qr_string, { errorCorrectionLevel: 'M', margin: 1, width: 560, color: { dark: '#000000', light: '#ffffff' } })
      .then(setQrSrc)
      .catch(() => setQrSrc(''))
  }, [p.qr_string])

  const amount = p.currency === 'KHR' ? formatKHR(p.amount_minor) : formatUSD(p.amount_minor)
  const isKhqr = p.method === 'abapay_khqr'

  async function simulate() {
    setSimulating(true)
    try {
      await api('/api/dev/payway-simulator/pay', { method: 'POST', body: { tran_id: p.tran_id } })
      await reload()
    } finally {
      setSimulating(false)
    }
  }

  return (
    <section className="mt-6 flex flex-col items-center">
      {/* KHQR-style card: red header, merchant, amount, QR (check against ABA's display guideline before launch) */}
      <div className="w-full max-w-[320px] overflow-hidden rounded-2xl bg-white text-[#1a1a1a] shadow-[0_8px_30px_rgba(0,0,0,0.12)]">
        <div className={`flex h-12 items-center justify-center text-sm font-bold tracking-[0.2em] text-white ${isKhqr ? 'bg-[#E1232E]' : p.method === 'wechat' ? 'bg-[#07C160]' : 'bg-[#1677FF]'}`}>
          {isKhqr ? 'KHQR' : t(`pay.${p.method}`)}
        </div>
        <div className="px-6 pt-4">
          <div className="text-xs text-[#666]">LAGOM</div>
          <div className="text-2xl font-bold tabular-nums">{amount}</div>
        </div>
        <div className="mx-6 my-3 border-t border-dashed border-[#ccc]" />
        <div className="px-6 pb-6">
          {qrSrc ? (
            <img src={qrSrc} alt="Payment QR code" className="aspect-square w-full" />
          ) : (
            <div className="skeleton aspect-square w-full rounded" />
          )}
        </div>
      </div>

      <p className="mt-5 max-w-xs text-center text-sm text-muted">
        {isKhqr ? t('pay.scan') : t('pay.scanWallet', { app: t(`pay.${p.method}`) })}
      </p>

      {isKhqr && isMobile && p.deeplink && (
        <a href={p.deeplink} className="mt-4 flex h-12 w-full max-w-[320px] items-center justify-center gap-2 rounded-full bg-brand font-semibold text-on-brand">
          <Smartphone size={18} /> {t('pay.openAba')}
        </a>
      )}

      <div className="mt-5 flex items-center gap-2 text-sm" aria-live="polite">
        <span className="relative flex size-2.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-60" />
          <span className="relative inline-flex size-2.5 rounded-full bg-accent" />
        </span>
        {t('pay.waiting')}
      </div>
      {remaining && <p className="mt-1 text-xs text-muted tabular-nums">{t('pay.expiresIn', { time: remaining })}</p>}

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
        <p className="mt-1 text-sm text-muted">{t('track.table')} · {order.table}</p>
        {!cancelled && current < 3 && (
          <p className="mt-3 inline-flex items-center gap-1.5 text-sm text-muted">
            <Clock size={14} /> {t('track.estimate', { n: order.estimated_ready_minutes })}
          </p>
        )}
      </section>

      {!cancelled && (
        <ol className="mx-auto mt-8 max-w-sm" aria-label="Order progress">
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
