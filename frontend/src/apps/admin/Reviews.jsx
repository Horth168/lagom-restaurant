/* Customer ratings: overall average, average per dish, latest comments. */
import { useEffect, useState } from 'react'
import { Star } from 'lucide-react'
import { Card, Skeleton } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const PERIODS = [30, 90, 365]

function StarRow({ value }) {
  return (
    <span className="inline-flex" aria-label={`${value} / 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star key={n} size={14} strokeWidth={1.5} className={n <= Math.round(value) ? 'fill-gold text-gold' : 'text-line'} />
      ))}
    </span>
  )
}

export default function Reviews() {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const [days, setDays] = useState(90)
  const [data, setData] = useState(null)

  useEffect(() => {
    staffApi(`/api/admin/reviews?days=${days}`).then(setData)
  }, [days, staffApi])

  return (
    <>
      <PageTitle title={t('admin.nav.reviews')}>
        {PERIODS.map((d) => (
          <button key={d} onClick={() => setDays(d)} aria-pressed={days === d}
            className={`h-9 rounded-full px-3 text-sm ${days === d ? 'bg-brand text-on-brand' : 'border border-line'}`}>
            {t('reviews.days', { n: d })}
          </button>
        ))}
      </PageTitle>
      {!data ? <Skeleton className="h-64" /> : (
        <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
          <Card title={t('reviews.dishes')}>
            <div className="mb-4 flex items-baseline gap-3">
              <span className="font-display text-5xl tabular-nums">{data.average ?? '—'}</span>
              <span className="text-sm text-muted">{t('reviews.overall', { n: data.count })}</span>
            </div>
            {data.dishes.length === 0 ? <p className="text-sm text-muted">{t('reviews.none')}</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-muted"><th className="py-2 font-medium">{t('reviews.dish')}</th><th className="py-2 font-medium">{t('reviews.rating')}</th><th className="py-2 text-right font-medium">{t('reviews.count')}</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {data.dishes.map((d) => (
                    <tr key={d.name}>
                      <td className="py-2">{d.name}</td>
                      <td className="py-2"><span className="inline-flex items-center gap-2"><StarRow value={d.average} /> <span className="tabular-nums">{d.average.toFixed(1)}</span></span></td>
                      <td className="py-2 text-right tabular-nums">{d.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          <Card title={t('reviews.recent')}>
            {data.recent.length === 0 ? <p className="text-sm text-muted">{t('reviews.none')}</p> : (
              <ul className="divide-y divide-line">
                {data.recent.map((r, i) => (
                  <li key={i} className="py-3">
                    <div className="flex items-center gap-2 text-sm">
                      <StarRow value={r.stars} />
                      <span className="font-medium">#{r.order}</span>
                      <span className="text-muted">{r.table} · {new Date(r.created_at).toLocaleString(appLocale(), { dateStyle: 'medium', timeStyle: 'short' })}</span>
                    </div>
                    {r.comment && <p className="mt-1 text-[15px]">“{r.comment}”</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </>
  )
}
