/* When are we busy? Paid orders by weekday × hour (restaurant time), last 4 weeks.
 * One hue, light → dark (more orders = darker). Hover or tap a square for the numbers. */
import { useEffect, useMemo, useState } from 'react'
import { Card } from '../../components/ui'
import { useI18n } from '../../i18n'
import { formatUSD } from '../../lib/money'
import { useStaff } from '../../lib/staffAuth'

const DAYS = [0, 1, 2, 3, 4, 5, 6]
// Opacity steps of the main series colour (sequential, single hue)
const STEPS = [0.14, 0.32, 0.5, 0.72, 1]

export function BusyHours() {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const [data, setData] = useState(null)
  const [days, setDays] = useState(28)
  const [hover, setHover] = useState(null)

  useEffect(() => {
    staffApi(`/api/admin/reports/hours?days=${days}`).then(setData).catch(() => setData(null))
  }, [days, staffApi])

  const { grid, hours, max } = useMemo(() => {
    const g = new Map((data?.cells ?? []).map((c) => [`${c.weekday}-${c.hour}`, c]))
    const used = (data?.cells ?? []).map((c) => c.hour)
    const lo = used.length ? Math.min(...used, 8) : 8
    const hi = used.length ? Math.max(...used, 21) : 21
    return { grid: g, hours: Array.from({ length: hi - lo + 1 }, (_, i) => lo + i), max: Math.max(1, ...(data?.cells ?? []).map((c) => c.orders)) }
  }, [data])

  const shade = (n) => (n ? STEPS[Math.min(STEPS.length - 1, Math.floor(((n - 1) / max) * STEPS.length))] : 0)
  const busiest = data?.busiest

  return (
    <Card title={t('busy.title')} className="lg:col-span-3"
      action={
        <div className="flex gap-1">
          {[28, 90].map((d) => (
            <button key={d} onClick={() => setDays(d)} aria-pressed={days === d}
              className={`h-8 rounded-full px-3 text-xs ${days === d ? 'bg-brand text-on-brand' : 'border border-line'}`}>{t('reviews.days', { n: d })}</button>
          ))}
        </div>
      }>
      {!data ? <div className="skeleton h-48 rounded-lg" /> : data.orders === 0 ? (
        <p className="text-sm text-muted">{t('admin.noSales')}</p>
      ) : (
        <>
          {busiest && (
            <p className="mb-4 text-sm">
              {t('busy.peak', { day: t(`day.${busiest.weekday}`), from: `${busiest.hour}:00`, to: `${busiest.hour + 1}:00`, n: busiest.orders })}
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="border-separate border-spacing-[3px] text-xs" aria-label={t('busy.title')}>
              <thead>
                <tr>
                  <th />
                  {hours.map((h) => <th key={h} scope="col" className="w-7 font-normal text-muted tabular-nums">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {DAYS.map((d) => (
                  <tr key={d}>
                    <th scope="row" className="pr-2 text-left font-normal text-muted">{t(`day.${d}`)}</th>
                    {hours.map((h) => {
                      const c = grid.get(`${d}-${h}`)
                      const n = c?.orders ?? 0
                      const label = `${t(`day.${d}`)} ${h}:00 · ${t('busy.orders', { n })}${c ? ` · ${formatUSD(c.sales_usd_cents)}` : ''}`
                      return (
                        <td key={h} className="p-0">
                          <button
                            aria-label={label}
                            onMouseEnter={() => setHover(label)} onMouseLeave={() => setHover(null)}
                            onFocus={() => setHover(label)} onBlur={() => setHover(null)} onClick={() => setHover(label)}
                            className="block size-7 rounded-[4px] border border-line/60 outline-offset-1"
                            style={n ? { background: `color-mix(in srgb, var(--series-1) ${shade(n) * 100}%, transparent)`, borderColor: 'transparent' } : undefined}
                          />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted">
            <span aria-live="polite" className="min-h-4 text-ink">{hover || t('busy.hint')}</span>
            <span className="flex items-center gap-1.5">
              {t('busy.fewer')}
              {STEPS.map((s) => <span key={s} className="size-3.5 rounded-[3px]" style={{ background: `color-mix(in srgb, var(--series-1) ${s * 100}%, transparent)` }} />)}
              {t('busy.more')}
            </span>
          </div>
        </>
      )}
    </Card>
  )
}
