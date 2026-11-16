/* "How was your meal?" — overall stars, optional stars per dish and a comment. Once per order. */
import { useEffect, useState } from 'react'
import { Star } from 'lucide-react'
import { useI18n } from '../../i18n'
import { api } from '../../lib/api'
import { useCustomer } from './CustomerContext'

function Stars({ value, onChange, size = 30, label }) {
  const { t } = useI18n()
  return (
    <div className="flex gap-1" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={t('review.starsN', { n })}
          onClick={() => onChange(n)} className="p-0.5">
          <Star size={size} strokeWidth={1.5} className={n <= value ? 'fill-gold text-gold' : 'text-line'} />
        </button>
      ))}
    </div>
  )
}

export function ReviewBox({ order }) {
  const { t, pick } = useI18n()
  const { headers } = useCustomer()
  const [existing, setExisting] = useState(undefined)
  const [stars, setStars] = useState(0)
  const [dish, setDish] = useState({})
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/api/public/orders/${order.public_id}/review`, { headers }).then(setExisting).catch(() => setExisting(null))
  }, [order.public_id, headers])

  if (existing === undefined) return null
  if (existing) {
    return (
      <section className="mt-8 rounded-2xl border border-line bg-surface p-5 text-center">
        <div className="flex justify-center"><Stars value={existing.stars} onChange={() => {}} size={22} label={t('review.title')} /></div>
        <p className="mt-2 text-sm text-muted">{t('review.thanks')}</p>
      </section>
    )
  }

  async function send() {
    setBusy(true)
    setError('')
    try {
      const items = Object.entries(dish).map(([item_id, s]) => ({ item_id: Number(item_id), stars: s }))
      await api(`/api/public/orders/${order.public_id}/review`, { method: 'POST', headers, body: { stars, comment, items } })
      setExisting({ stars, comment })
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-8 rounded-2xl border border-line bg-surface p-5">
      <h2 className="font-display text-xl">{t('review.title')}</h2>
      <div className="mt-3"><Stars value={stars} onChange={setStars} label={t('review.title')} /></div>
      {stars > 0 && (
        <>
          {order.items.length > 1 && (
            <ul className="mt-5 space-y-3">
              {order.items.map((i) => (
                <li key={i.id} className="flex items-center justify-between gap-3">
                  <span className="text-sm">{pick(i.name)}</span>
                  <Stars value={dish[i.id] || 0} onChange={(n) => setDish((d) => ({ ...d, [i.id]: n }))} size={20} label={pick(i.name)} />
                </li>
              ))}
            </ul>
          )}
          <textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} rows={3}
            placeholder={t('review.comment')}
            className="mt-4 w-full rounded-xl border border-line bg-bg p-3 text-[15px] outline-none focus:border-accent" />
          {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
          <button onClick={send} disabled={busy}
            className="mt-3 h-12 w-full rounded-full bg-brand font-semibold text-on-brand disabled:opacity-60">
            {t('review.send')}
          </button>
        </>
      )}
    </section>
  )
}
