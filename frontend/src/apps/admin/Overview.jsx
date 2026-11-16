import { Segmented } from '../../components/Segmented'
import { BusyHours } from './BusyHours'
import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Card, inputBase, Skeleton } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { formatUSD } from '../../lib/money'
import { useLiveChannel } from '../../lib/realtime'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const PERIODS = ['today', 'yesterday', '7d', '30d', 'month', 'custom']

export default function Overview() {
  const { t } = useI18n()
  const { staffApi, token, can } = useStaff()
  const [period, setPeriod] = useState('today')
  const [range, setRange] = useState({ start: '', end: '' })
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (period === 'custom' && !(range.start && range.end)) return
    const q = period === 'custom' ? `period=custom&start=${range.start}&end=${range.end}` : `period=${period}`
    try {
      setData(await staffApi(`/api/admin/dashboard?${q}`))
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [period, range, staffApi])

  useEffect(() => {
    load()
  }, [load])
  // Numbers update by themselves when an order is paid or changes
  useLiveChannel('/api/ws/staff', { token, station: null }, () => load(), can('orders.view'))

  return (
    <>
      <PageTitle title={t('admin.nav.overview')}>
        <Segmented label={t('admin.periodLabel')} value={period} onChange={setPeriod}
          options={PERIODS.map((p) => ({ value: p, label: t(`admin.period.${p}`) }))} />
        {period === 'custom' && (
          <div className="flex items-center gap-2">
            <input type="date" className={`${inputBase} w-40`} value={range.start} onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} aria-label={t('admin.from')} />
            <span className="text-muted">–</span>
            <input type="date" className={`${inputBase} w-40`} value={range.end} onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} aria-label={t('admin.to')} />
          </div>
        )}
      </PageTitle>

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      {!data ? (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <Stat label={t('admin.stat.revenue')} value={formatUSD(data.revenue_usd_cents)} hero />
            <Stat label={t('admin.stat.orders')} value={data.orders} />
            <Stat label={t('admin.stat.average')} value={formatUSD(data.average_order_usd_cents)} />
            <Stat label={t('admin.stat.discounts')} value={formatUSD(data.discounts_usd_cents)} />
            <Stat label={t('admin.stat.inProgress')} value={data.in_progress} />
            <Stat label={t('admin.stat.pending')} value={data.pending_payment} />
            <Stat label={t('admin.stat.completed')} value={data.completed} />
            <Stat label={t('admin.stat.cancelled')} value={data.cancelled} />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title={t(data.period.by === 'hour' ? 'admin.chart.byHour' : 'admin.chart.byDay')} className="lg:col-span-2">
              <SalesChart points={data.sales_chart} byHour={data.period.by === 'hour'} />
            </Card>
            <Card title={t('admin.payments')}>
              <PaymentSplit payments={data.payments} />
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title={t('admin.bestSellers')}>
              <BestSellers rows={data.best_sellers} />
            </Card>
            <Card title={t('admin.tables')}>
              <ul className="max-h-80 divide-y divide-line overflow-y-auto text-sm">
                {data.tables.map((r) => (
                  <li key={r.table} className="flex items-center justify-between py-2">
                    <span>{r.table}</span>
                    <span className="flex items-center gap-3 tabular-nums text-muted">
                      {r.open_orders > 0 && <span className="rounded-full bg-series-1/15 px-2 text-xs font-semibold text-series-1">{t('admin.openNow', { n: r.open_orders })}</span>}
                      {t('admin.ordersCount', { n: r.orders })} · <span className="text-ink">{formatUSD(r.usd_cents)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title={t('admin.lowStock')}>
              {data.low_stock.length === 0 ? (
                <p className="text-sm text-muted">{t('admin.lowStockNone')}</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {data.low_stock.map((i) => (
                    <li key={i.id} className="flex items-center gap-2">
                      <AlertTriangle size={16} className="text-series-2" aria-label={t('admin.lowStock')} />
                      <span className="flex-1">{i.name}</span>
                      <span className="tabular-nums text-muted">{Number(i.quantity)} / {Number(i.threshold)} {i.unit}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <BusyHours />
          </div>
        </div>
      )}
    </>
  )
}

function Stat({ label, value, hero }) {
  return (
    <div className={`min-w-0 rounded-xl border border-line p-4 transition-shadow hover:shadow-[0_4px_20px_rgba(0,0,0,0.06)] sm:p-5 ${hero ? 'col-span-2 bg-forest text-cream sm:col-span-1' : 'bg-surface'}`}>
      <div className={`truncate text-xs sm:text-sm ${hero ? 'text-cream/75' : 'text-muted'}`}>{label}</div>
      <div className={`mt-1.5 font-display tabular-nums sm:mt-2 ${hero ? 'text-3xl sm:text-4xl' : 'text-2xl sm:text-3xl'}`}>{value}</div>
    </div>
  )
}

/** Single-series bar chart: one hue, no legend (the title names it), hover tooltip per bar. */
function SalesChart({ points, byHour }) {
  const { t } = useI18n()
  const [hover, setHover] = useState(null)
  const W = 720, H = 240, L = 48, B = 26, T = 10
  const max = Math.max(...points.map((p) => p.usd_cents), 1)
  const nice = niceMax(max)
  const step = (W - L) / points.length
  const bw = Math.max(2, Math.min(28, step - 4))
  const y = (v) => T + (H - T - B) * (1 - v / nice)
  const label = (p) => (byHour ? `${p.label}:00` : new Date(p.label + 'T00:00').toLocaleDateString(appLocale(), { day: 'numeric', month: 'short' }))
  const every = Math.ceil(points.length / 8)
  if (!points.some((p) => p.usd_cents)) return <p className="py-16 text-center text-sm text-muted">{t('admin.noSales')}</p>
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t(byHour ? 'admin.chart.byHour' : 'admin.chart.byDay')}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={L} x2={W} y1={y(nice * f)} y2={y(nice * f)} stroke="var(--grid)" strokeWidth="1" />
            <text x={L - 8} y={y(nice * f) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{formatUSD(nice * f).replace('.00', '')}</text>
          </g>
        ))}
        {points.map((p, i) => {
          const x = L + i * step + (step - bw) / 2
          const h = Math.max(0, H - B - y(p.usd_cents))
          return (
            <g key={p.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={L + i * step} y={T} width={step} height={H - T - B} fill="transparent" />
              {p.usd_cents > 0 && (
                <path d={roundedTop(x, H - B - h, bw, h, Math.min(4, bw / 2))} fill="var(--series-1)" opacity={hover === null || hover === i ? 1 : 0.45} />
              )}
              {i % every === 0 && <text x={L + i * step + step / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)">{label(p)}</text>}
            </g>
          )
        })}
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 rounded-lg bg-ink px-3 py-1.5 text-xs text-bg shadow-lg"
          style={{ left: `${((L + hover * step + step / 2) / W) * 100}%`, top: 0 }}
        >
          <div className="font-semibold tabular-nums">{formatUSD(points[hover].usd_cents)}</div>
          <div className="opacity-75">{label(points[hover])}</div>
        </div>
      )}
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-muted">{t('admin.showTable')}</summary>
        <table className="mt-2 w-full text-left tabular-nums">
          <tbody>
            {points.filter((p) => p.usd_cents).map((p) => (
              <tr key={p.label} className="border-t border-line"><td className="py-1">{label(p)}</td><td className="py-1 text-right">{formatUSD(p.usd_cents)}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

function roundedTop(x, y, w, h, r) {
  if (h < r) r = h
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`
}

function niceMax(v) {
  const p = 10 ** Math.floor(Math.log10(v))
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((n) => n >= v)
}

/** Two categories: segmented bar with a 2px gap, plus a legend that also carries the numbers. */
function PaymentSplit({ payments }) {
  const { t } = useI18n()
  const rows = [
    { key: 'ABA_KHQR', label: t('pay.khqr'), color: 'var(--series-1)' },
    { key: 'CASH', label: t('pay.cash'), color: 'var(--series-2)' },
  ].map((r) => ({ ...r, ...(payments[r.key] || { orders: 0, usd_cents: 0 }) }))
  const total = rows.reduce((s, r) => s + r.usd_cents, 0)
  if (!total) return <p className="py-10 text-center text-sm text-muted">{t('admin.noSales')}</p>
  return (
    <div>
      <div className="flex h-4 gap-[2px] overflow-hidden rounded" role="img" aria-label={rows.map((r) => `${r.label} ${Math.round((r.usd_cents / total) * 100)}%`).join(', ')}>
        {rows.filter((r) => r.usd_cents).map((r) => (
          <div key={r.key} style={{ width: `${(r.usd_cents / total) * 100}%`, background: r.color }} />
        ))}
      </div>
      <ul className="mt-5 space-y-3">
        {rows.map((r) => (
          <li key={r.key} className="flex items-center gap-3 text-sm">
            <span className="size-3 rounded-sm" style={{ background: r.color }} aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate">{r.label}<span className="block text-xs text-muted tabular-nums">{t('admin.ordersCount', { n: r.orders })}</span></span>
            <span className="w-20 text-right font-semibold tabular-nums">{formatUSD(r.usd_cents)}</span>
            <span className="w-10 text-right tabular-nums text-muted">{Math.round((r.usd_cents / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function BestSellers({ rows }) {
  const { t } = useI18n()
  if (!rows.length) return <p className="text-sm text-muted">{t('admin.noSales')}</p>
  const max = rows[0].quantity
  return (
    <ol className="space-y-3">
      {rows.map((r, i) => (
        <li key={r.name} className="text-sm">
          <div className="flex justify-between gap-2">
            <span><span className="mr-2 text-muted tabular-nums">{i + 1}</span>{r.name}</span>
            <span className="tabular-nums text-muted">{r.quantity} · <span className="text-ink">{formatUSD(r.revenue_usd_cents)}</span></span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-series-1" style={{ width: `${(r.quantity / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ol>
  )
}
