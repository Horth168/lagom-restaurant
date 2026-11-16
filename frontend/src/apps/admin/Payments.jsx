import { useCallback, useEffect, useState } from 'react'
import { Badge, Button, Card, inputCls, parseUsd, Skeleton, useToast } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { formatKHR, formatUSD } from '../../lib/money'
import { useLiveChannel } from '../../lib/realtime'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'
import { OrderDetail } from './Orders'

/** Waiting orders (take cash), ABA payments LAGOM could not match, refunds to give back, listener status. */
export default function Payments() {
  const { t } = useI18n()
  const { staffApi, token, can } = useStaff()
  const toast = useToast()
  const [waiting, setWaiting] = useState(null)
  const [notices, setNotices] = useState([])
  const [refunds, setRefunds] = useState([])
  const [setup, setSetup] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [assign, setAssign] = useState({})

  const load = useCallback(async () => {
    const [w, n, r, s] = await Promise.all([
      staffApi('/api/admin/payments/waiting'),
      staffApi('/api/admin/bank-notices'),
      staffApi('/api/admin/refunds'),
      staffApi('/api/admin/payments/status'),
    ])
    setWaiting(w)
    setNotices(n)
    setRefunds(r)
    setSetup(s)
  }, [staffApi])

  useEffect(() => {
    load()
  }, [load])
  useLiveChannel('/api/ws/staff', { token, station: null }, () => load())

  async function doAssign(notice) {
    try {
      await staffApi(`/api/admin/bank-notices/${notice.id}/assign`, { method: 'POST', body: { order_public_id: assign[notice.id] } })
      toast(t('admin.pay.assigned'))
      load()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  async function refundDone(r) {
    const reference = window.prompt(t('admin.pay.refundRef'), r.method === 'cash' ? 'cash' : '')
    if (reference === null) return
    try {
      await staffApi(`/api/admin/refunds/${r.id}/complete`, { method: 'POST', body: { reference } })
      toast(t('admin.pay.refundRecorded'))
      load()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  const open = notices.filter((n) => n.outcome === 'ambiguous' || n.outcome === 'unmatched')
  const khqrWaiting = (waiting || []).filter((w) => w.method === 'khqr')

  return (
    <>
      <PageTitle title={t('admin.nav.payments')}>
        {setup && (
          <Badge tone={setup.listener.state === 'connected' ? 'good' : setup.listener_configured ? 'warn' : 'neutral'}>
            {t('admin.pay.listener')}: {setup.listener_configured ? setup.listener.state : t('admin.pay.notSetUp')}
          </Badge>
        )}
      </PageTitle>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t('admin.pay.waiting')}>
          {!waiting ? <Skeleton className="h-32" /> : waiting.length === 0 ? (
            <p className="text-sm text-muted">{t('admin.pay.noneWaiting')}</p>
          ) : (
            <ul className="divide-y divide-line">
              {waiting.map((w) => (
                <li key={w.public_id}>
                  <button onClick={() => setOpenId(w.public_id)} className="flex w-full items-center gap-3 py-3 text-left hover:bg-surface-2">
                    <span className="font-display text-2xl tabular-nums">#{w.number}</span>
                    <span className="flex-1 text-sm">
                      {w.table || t('kds.takeaway')}
                      <span className="block text-xs text-muted">{w.method ? t(`pay.${w.method}`) : t('admin.pay.notChosen')} · {w.reference || ''}</span>
                    </span>
                    <span className="text-right text-sm font-semibold tabular-nums">
                      {formatUSD(w.total_usd_cents)}
                      <span className="block text-xs font-normal text-muted">{formatKHR(w.total_khr)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={t('admin.pay.notices')}>
          <p className="mb-3 text-xs text-muted">{t('admin.pay.noticesHint')}</p>
          {open.length === 0 ? (
            <p className="text-sm text-muted">{t('admin.pay.noNotices')}</p>
          ) : (
            <ul className="space-y-3">
              {open.map((n) => (
                <li key={n.id} className="rounded-lg border border-line p-3 text-sm">
                  <div className="flex justify-between">
                    <span className="font-semibold">{n.currency === 'KHR' ? formatKHR(n.amount_minor) : formatUSD(n.amount_minor)} · {n.payer}</span>
                    <Badge tone="warn">{t(`admin.pay.${n.outcome}`)}</Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted">ABA Trx {n.trx_id} · {new Date(n.received_at).toLocaleString(appLocale())}</div>
                  {can('payments.cash') && (
                    <div className="mt-2 flex gap-2">
                      <select className={inputCls} value={assign[n.id] || ''} onChange={(e) => setAssign((a) => ({ ...a, [n.id]: e.target.value }))} aria-label={t('admin.pay.chooseOrder')}>
                        <option value="">{t('admin.pay.chooseOrder')}</option>
                        {khqrWaiting.filter((w) => w.amount_minor === n.amount_minor && w.currency === n.currency).map((w) => (
                          <option key={w.public_id} value={w.public_id}>#{w.number} · {w.table || t('kds.takeaway')}</option>
                        ))}
                      </select>
                      <Button variant="primary" disabled={!assign[n.id]} onClick={() => doAssign(n)}>{t('admin.pay.assign')}</Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        {refunds.length > 0 && (
          <Card title={t('admin.pay.refunds')} className="lg:col-span-2">
            <ul className="divide-y divide-line text-sm">
              {refunds.map((r) => (
                <li key={r.id} className="flex items-center gap-3 py-3">
                  <span className="font-semibold">#{r.number}</span>
                  <span className="flex-1">{r.reason}<span className="block text-xs text-muted">{t(`pay.${r.method}`)}{r.bank_reference && ` · ABA Trx ${r.bank_reference}`}</span></span>
                  <span className="font-semibold tabular-nums">{r.currency === 'KHR' ? formatKHR(r.amount_minor) : formatUSD(r.amount_minor)}</span>
                  {can('payments.refund') && <Button size="sm" onClick={() => refundDone(r)}>{t('admin.pay.markRefunded')}</Button>}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
      <ShiftHistory />
      <OrderDetail publicId={openId} onClose={() => setOpenId(null)} onChanged={load} />
    </>
  )
}

/** Cash drawer shifts: expected vs counted, so missing cash is visible to the owner. */
function ShiftHistory() {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const [rows, setRows] = useState(null)
  useEffect(() => {
    staffApi('/api/admin/shifts').then(setRows).catch(() => setRows([]))
  }, [staffApi])
  if (!rows) return null
  const when = (d) => new Date(d).toLocaleString(appLocale(), { dateStyle: 'medium', timeStyle: 'short' })
  return (
    <Card title={t('shift.history')} className="mt-6">
      {rows.length === 0 ? <p className="text-sm text-muted">{t('shift.none')}</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-2 font-medium">{t('shift.when')}</th>
                <th className="py-2 font-medium">{t('shift.who')}</th>
                <th className="py-2 text-right font-medium">{t('shift.expected')}</th>
                <th className="py-2 text-right font-medium">{t('shift.counted')}</th>
                <th className="py-2 text-right font-medium">{t('shift.difference')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((s) => {
                const du = s.difference_usd_cents
                const dk = s.difference_khr
                return (
                  <tr key={s.id}>
                    <td className="py-2">{when(s.opened_at)}{s.closed_at ? ` → ${new Date(s.closed_at).toLocaleTimeString(appLocale(), { hour: '2-digit', minute: '2-digit' })}` : ''}</td>
                    <td className="py-2">{s.closed_by || s.opened_by}{s.note && <span className="block text-xs text-muted">“{s.note}”</span>}</td>
                    <td className="py-2 text-right tabular-nums">{formatUSD(s.expected_usd_cents)}{s.expected_khr ? <span className="block text-xs text-muted">{formatKHR(s.expected_khr)}</span> : null}</td>
                    <td className="py-2 text-right tabular-nums">{s.status === 'OPEN' ? <Badge tone="info">{t('shift.stillOpen')}</Badge> : <>{formatUSD(s.counted_usd_cents)}{s.counted_khr ? <span className="block text-xs text-muted">{formatKHR(s.counted_khr)}</span> : null}</>}</td>
                    <td className={`py-2 text-right font-semibold tabular-nums ${du || dk ? 'text-danger' : 'text-series-1'}`}>
                      {s.status === 'OPEN' ? '—' : du === 0 && dk === 0 ? '✓' : `${du >= 0 ? '+' : '−'}${formatUSD(Math.abs(du))}${dk ? ` · ${dk > 0 ? '+' : '−'}${formatKHR(Math.abs(dk))}` : ''}`}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/** Cash at the counter: amount received in USD or riel, change shown before confirming. */
export function CashForm({ order, onDone, autoFocus = true }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [currency, setCurrency] = useState('USD')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const due = currency === 'KHR' ? order.total_khr : order.total_usd_cents
  const received = currency === 'KHR' ? (/^\d+$/.test(text.replace(/[,\s៛]/g, '')) ? Number(text.replace(/[,\s៛]/g, '')) : null) : parseUsd(text)
  const fmt = (v) => (currency === 'KHR' ? formatKHR(v) : formatUSD(v))
  const quick = currency === 'KHR' ? [due, Math.ceil(due / 10000) * 10000, Math.ceil(due / 50000) * 50000, 100000] : [due, Math.ceil(due / 500) * 500, Math.ceil(due / 1000) * 1000, Math.ceil(due / 2000) * 2000]

  async function submit() {
    setBusy(true)
    try {
      const r = await staffApi(`/api/admin/orders/${order.public_id}/cash`, { method: 'POST', body: { currency, received_minor: received } })
      toast(t('admin.cashDone', { change: fmt(r.change_minor) }))
      await onDone?.(r)
    } catch (e) {
      toast(e.message, 'bad')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {['USD', 'KHR'].map((c) => (
          <button key={c} onClick={() => { setCurrency(c); setText('') }} className={`h-10 flex-1 rounded-lg border text-sm font-semibold ${currency === c ? 'border-brand bg-brand text-on-brand' : 'border-line bg-surface'}`}>
            {c === 'USD' ? formatUSD(order.total_usd_cents) : formatKHR(order.total_khr)}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {[...new Set(quick)].map((q) => (
          <Button key={q} size="sm" onClick={() => setText(currency === 'KHR' ? String(q) : (q / 100).toFixed(2))}>{fmt(q)}</Button>
        ))}
      </div>
      <input
        inputMode="decimal"
        autoFocus={autoFocus}
        className={`${inputCls} h-12 text-lg tabular-nums`}
        placeholder={t('pos.received')}
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label={t('pos.received')}
      />
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted">{t('pos.change')}</span>
        <span className={`text-xl font-semibold tabular-nums ${received != null && received < due ? 'text-danger' : ''}`}>
          {received == null ? '—' : received < due ? t('pos.notEnough') : fmt(received - due)}
        </span>
      </div>
      <Button variant="primary" size="lg" className="w-full" disabled={busy || received == null || received < due} onClick={submit}>
        {t('pos.confirmCash')}
      </Button>
    </div>
  )
}
