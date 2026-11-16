import { useCallback, useEffect, useState } from 'react'
import { Printer, Search } from 'lucide-react'
import { Receipt, printSoon } from '../../components/Receipt'
import { Sheet } from '../../components/Sheet'
import { Badge, Button, Card, Field, inputCls, Skeleton, STATUS_TONE, useToast } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { formatKHR, formatUSD } from '../../lib/money'
import { useLiveChannel } from '../../lib/realtime'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'
import { CashForm } from './Payments'

const STATUSES = ['', 'PENDING_PAYMENT', 'PAID', 'PREPARING', 'READY', 'SERVED', 'CANCELLED', 'EXPIRED']

export default function Orders() {
  const { t } = useI18n()
  const { staffApi, token } = useStaff()
  const [filters, setFilters] = useState({ status: '', start: '', end: '', q: '' })
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [openId, setOpenId] = useState(null)

  const load = useCallback(async () => {
    const qs = new URLSearchParams({ page: String(page), per_page: '30' })
    Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v))
    try {
      setData(await staffApi(`/api/admin/orders?${qs}`))
    } catch {
      /* keep last data */
    }
  }, [filters, page, staffApi])

  useEffect(() => {
    const id = setTimeout(load, 250) // small delay while typing in search
    return () => clearTimeout(id)
  }, [load])
  useLiveChannel('/api/ws/staff', { token, station: null }, () => load())

  const set = (k) => (e) => {
    setPage(1)
    setFilters((f) => ({ ...f, [k]: e.target.value }))
  }
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1

  return (
    <>
      <PageTitle title={t('admin.nav.orders')} />
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="relative block">
            <Search size={16} className="absolute top-3 left-3 text-muted" />
            <input className={`${inputCls} pl-9`} placeholder={t('admin.orders.search')} value={filters.q} onChange={set('q')} aria-label={t('admin.orders.search')} />
          </label>
          <select className={inputCls} value={filters.status} onChange={set('status')} aria-label={t('admin.orders.status')}>
            {STATUSES.map((s) => <option key={s} value={s}>{s ? t(`status.${s}`) : t('admin.orders.allStatuses')}</option>)}
          </select>
          <input type="date" className={inputCls} value={filters.start} onChange={set('start')} aria-label={t('admin.from')} />
          <input type="date" className={inputCls} value={filters.end} onChange={set('end')} aria-label={t('admin.to')} />
        </div>

        {!data ? (
          <Skeleton className="h-64" />
        ) : data.orders.length === 0 ? (
          <p className="py-12 text-center text-muted">{t('admin.orders.none')}</p>
        ) : (
          <>
          {/* Phones: one card per order */}
          <ul className="-mx-1 divide-y divide-line md:hidden">
            {data.orders.map((o) => (
              <li key={o.public_id}>
                <button onClick={() => setOpenId(o.public_id)} className="press flex w-full items-center gap-3 rounded-lg px-1 py-3 text-left active:bg-surface-2">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-surface-2 text-sm font-semibold tabular-nums">#{o.number}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{o.table || t(`channel.${o.channel}`)}</span>
                    <span className="block truncate text-xs text-muted">
                      {new Date(o.created_at).toLocaleString(appLocale(), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      {' · '}{t('admin.orders.itemsN', { n: o.items_count })}
                      {o.payment_method && <> · {t(`pay.${o.payment_method}`)}</>}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    <span className="font-semibold tabular-nums">{formatUSD(o.total_usd_cents)}</span>
                    <Badge tone={STATUS_TONE[o.status]}>{t(`status.${o.status}`)}</Badge>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="-mx-5 hidden overflow-x-auto md:block">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-line text-xs uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-5 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">{t('admin.orders.time')}</th>
                  <th className="px-3 py-2 font-medium">{t('admin.orders.where')}</th>
                  <th className="px-3 py-2 font-medium">{t('admin.orders.items')}</th>
                  <th className="px-3 py-2 font-medium">{t('admin.orders.payment')}</th>
                  <th className="px-3 py-2 font-medium">{t('admin.orders.status')}</th>
                  <th className="px-5 py-2 text-right font-medium">{t('cart.total')}</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((o) => (
                  <tr key={o.public_id} onClick={() => setOpenId(o.public_id)} className="cursor-pointer border-b border-line last:border-0 hover:bg-surface-2">
                    <td className="px-5 py-3 font-semibold tabular-nums">{o.number}</td>
                    <td className="px-3 py-3 text-muted tabular-nums">{new Date(o.created_at).toLocaleString(appLocale(), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                    <td className="px-3 py-3">{o.table || t(`channel.${o.channel}`)}</td>
                    <td className="px-3 py-3 tabular-nums">{o.items_count}</td>
                    <td className="px-3 py-3">{o.payment_method ? t(`pay.${o.payment_method}`) : '—'}</td>
                    <td className="px-3 py-3"><Badge tone={STATUS_TONE[o.status]}>{t(`status.${o.status}`)}</Badge></td>
                    <td className="px-5 py-3 text-right font-semibold tabular-nums">{formatUSD(o.total_usd_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
        {data && pages > 1 && (
          <div className="mt-4 flex items-center justify-end gap-2 text-sm">
            <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('admin.prev')}</Button>
            <span className="tabular-nums text-muted">{page} / {pages}</span>
            <Button size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>{t('admin.next')}</Button>
          </div>
        )}
      </Card>
      <OrderDetail publicId={openId} onClose={() => setOpenId(null)} onChanged={load} />
    </>
  )
}

export function OrderDetail({ publicId, onClose, onChanged }) {
  const { t } = useI18n()
  const { staffApi, can } = useStaff()
  const toast = useToast()
  const [o, setO] = useState(null)
  const [reason, setReason] = useState('')
  const [cancelling, setCancelling] = useState(false)

  const load = useCallback(async () => {
    if (!publicId) return
    setO(await staffApi(`/api/admin/orders/${publicId}`))
  }, [publicId, staffApi])

  useEffect(() => {
    setO(null)
    setCancelling(false)
    setReason('')
    load()
  }, [load])

  async function cancel() {
    try {
      await staffApi(`/api/admin/orders/${publicId}/cancel`, { method: 'POST', body: { reason } })
      toast(t('admin.orders.cancelled'))
      setCancelling(false)
      await load()
      onChanged?.()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  const paid = o?.payments.some((p) => p.status === 'APPROVED')
  const canCancel = o && !['CANCELLED', 'EXPIRED'].includes(o.status) && can('orders.cancel') && (!paid || can('payments.refund'))

  return (
    <Sheet open={!!publicId} onClose={onClose} label={t('admin.orders.detail')}>
      {!o ? (
        <div className="p-6"><Skeleton className="h-60" /></div>
      ) : (
        <div className="p-6">
          <div className="flex items-start justify-between gap-3 pr-10">
            <div>
              <h2 className="font-display text-3xl">#{o.number}</h2>
              <p className="text-sm text-muted">{o.table || t(`channel.${o.channel}`)} · {new Date(o.created_at).toLocaleString(appLocale())}</p>
            </div>
            <Badge tone={STATUS_TONE[o.status]}>{t(`status.${o.status}`)}</Badge>
          </div>

          <ul className="mt-5 divide-y divide-line text-sm">
            {o.items.map((i) => (
              <li key={i.id} className="flex justify-between gap-3 py-2.5">
                <span>
                  <span className="font-medium">{i.quantity} × {i.name}</span>
                  {i.options.length > 0 && <span className="block text-muted">{i.options.join(' · ')}</span>}
                  {i.special_instructions && <span className="block italic text-muted">“{i.special_instructions}”</span>}
                  <span className="block text-xs text-muted">{t(`kds.station.${i.station}`)} · {t(`itemStatus.${i.status}`)}</span>
                </span>
                <span className="tabular-nums">{formatUSD(i.line_total_usd_cents)}</span>
              </li>
            ))}
          </ul>
          <dl className="mt-3 space-y-1 border-t border-line pt-3 text-sm">
            {o.discount_usd_cents > 0 && (
              <div className="flex justify-between text-muted"><dt>{t('pos.discount')} {o.discount_reason && `(${o.discount_reason})`}</dt><dd>-{formatUSD(o.discount_usd_cents)}</dd></div>
            )}
            <div className="flex justify-between text-base font-semibold"><dt>{t('cart.total')}</dt><dd className="tabular-nums">{formatUSD(o.total_usd_cents)} · {formatKHR(o.total_khr)}</dd></div>
          </dl>
          {o.customer_note && <p className="mt-3 rounded-lg bg-surface-2 p-3 text-sm">{o.customer_note}</p>}

          <h3 className="mt-6 text-sm font-semibold">{t('admin.orders.payment')}</h3>
          {o.payments.length === 0 && <p className="mt-1 text-sm text-muted">—</p>}
          <ul className="mt-2 space-y-2 text-sm">
            {o.payments.map((p) => (
              <li key={p.id} className="rounded-lg border border-line p-3">
                <div className="flex justify-between">
                  <span className="font-medium">{t(`pay.${p.method}`)} · {p.currency === 'KHR' ? formatKHR(p.amount_minor) : formatUSD(p.amount_minor)}</span>
                  <Badge tone={p.status === 'APPROVED' ? 'good' : p.status === 'PENDING' ? 'warn' : 'neutral'}>{t(`payStatus.${p.status}`)}</Badge>
                </div>
                <div className="mt-1 text-xs text-muted">
                  {t('admin.orders.ref')} {p.reference}
                  {p.bank_reference && ` · ABA Trx ${p.bank_reference}`}
                  {p.received_by && ` · ${p.received_by}`}
                  {p.change_given_minor != null && ` · ${t('pos.change')} ${p.currency === 'KHR' ? formatKHR(p.change_given_minor) : formatUSD(p.change_given_minor)}`}
                </div>
                {p.refunds.map((r) => (
                  <div key={r.id} className="mt-1 text-xs text-danger">{t('admin.refund')} {r.status}: {r.reason}</div>
                ))}
              </li>
            ))}
          </ul>

          {o.status === 'PENDING_PAYMENT' && can('payments.cash') && (
            <div className="mt-5 rounded-xl bg-surface-2 p-4">
              <h3 className="mb-3 text-sm font-semibold">{t('admin.takeCash')}</h3>
              <CashForm order={o} onDone={async () => { await load(); onChanged?.() }} />
            </div>
          )}

          {o.cancel_reason && <p className="mt-4 text-sm text-danger">{t('admin.orders.cancelReason')}: {o.cancel_reason} ({o.cancelled_by})</p>}

          <div className="mt-6 flex flex-wrap gap-2">
            <Button onClick={printSoon}><Printer size={16} /> {t('admin.printReceipt')}</Button>
            {canCancel && !cancelling && <Button variant="danger" onClick={() => setCancelling(true)}>{t('admin.orders.cancel')}</Button>}
          </div>
          {cancelling && (
            <div className="mt-4 space-y-3 rounded-xl border border-danger/40 p-4">
              <Field label={t('admin.orders.cancelReason')} hint={paid ? t('admin.orders.refundHint') : undefined}>
                <input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
              </Field>
              <div className="flex gap-2">
                <Button variant="danger" disabled={reason.trim().length < 3} onClick={cancel}>{t('admin.orders.confirmCancel')}</Button>
                <Button variant="ghost" onClick={() => setCancelling(false)}>{t('common.back')}</Button>
              </div>
            </div>
          )}
          <Receipt order={o} />
        </div>
      )}
    </Sheet>
  )
}
