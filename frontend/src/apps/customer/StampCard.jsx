/* Telegram stamp card: "7 / 9 stamps · 1 free item". Only for Telegram (pickup) customers. */
import { useEffect, useState } from 'react'
import { Gift, Stamp } from 'lucide-react'
import { useI18n } from '../../i18n'
import { api } from '../../lib/api'
import { useCustomer } from './CustomerContext'

export function useStampCard() {
  const { session, headers } = useCustomer()
  const [card, setCard] = useState(null)
  const pickup = !!session?.pickup
  useEffect(() => {
    if (pickup) api('/api/public/loyalty', { headers }).then(setCard).catch(() => setCard(null))
  }, [pickup, headers])
  return card?.enabled ? card : null
}

export function StampCard() {
  const { t, pick } = useI18n()
  const { menu } = useCustomer()
  const card = useStampCard()
  if (!card) return null
  const cats = menu.categories.filter((c) => card.category_ids.includes(c.id)).map((c) => pick(c.name)).join(', ')
  return (
    <section className="mx-4 mt-4 rounded-2xl border border-line bg-surface p-4" aria-label={t('loyalty.cardTitle')}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-medium"><Stamp size={18} className="text-accent" /> {t('loyalty.cardTitle')}</h2>
        <span className="text-sm tabular-nums text-muted">{card.stamps} / {card.needed}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5" aria-hidden="true">
        {Array.from({ length: card.needed }, (_, i) => (
          <span key={i} className={`size-6 rounded-full border-2 ${i < card.stamps ? 'border-accent bg-accent' : 'border-line'}`} />
        ))}
      </div>
      <p className="mt-3 text-sm text-muted">{t('loyalty.cardHint', { n: card.needed, cats })}</p>
      {card.rewards > 0 && (
        <p className="mt-2 flex items-center gap-2 text-sm font-semibold text-series-1">
          <Gift size={16} /> {t('loyalty.ready', { n: card.rewards })}
        </p>
      )}
    </section>
  )
}
