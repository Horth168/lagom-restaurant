import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Clock, Plus, ShoppingBag, Trash2 } from 'lucide-react'
import { ProductImage } from '../../components/ProductImage'
import { useI18n } from '../../i18n'
import { api, ApiError } from '../../lib/api'
import { formatKHR, formatPrice, formatUSD } from '../../lib/money'
import { useCustomer } from './CustomerContext'
import { Header } from './Header'
import { Stepper } from './ProductSheet'

export function CartPage() {
  const { t, pick } = useI18n()
  const { lines, setQty, productsById, categoriesById, settings } = useCustomer()
  const [result, setResult] = useState({ quote: null, problem: null, forLines: null })
  // Only trust a server answer that belongs to the cart exactly as it is now
  const fresh = result.forLines === lines
  const quote = fresh ? result.quote : null
  const problem = fresh ? result.problem : null
  const loading = lines.length > 0 && !fresh
  const setQuote = (q) => setResult({ quote: q, problem: null, forLines: lines })
  const setProblem = (p) => setResult({ quote: null, problem: p, forLines: lines })

  // Ask the server to price the cart every time it changes (debounced)
  useEffect(() => {
    if (!lines.length) return
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      api('/api/public/cart/quote', {
        method: 'POST',
        signal: ctrl.signal,
        body: {
          items: lines.map((l) => ({
            product_id: l.product_id,
            option_ids: l.option_ids,
            quantity: l.quantity,
            special_instructions: l.special_instructions,
          })),
        },
      })
        .then((q) => setQuote(q))
        .catch((e) => {
          if (e.name === 'AbortError') return
          setProblem(e instanceof ApiError && e.detail?.line !== undefined ? e.detail : { line: null, message: t('entry.offline') })
        })
    }, 250)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setters capture `lines`, which is already a dependency
  }, [lines, t])

  if (!lines.length) {
    return (
      <div className="min-h-dvh">
        <Header title={t('cart.title')} backTo=".." />
        <div className="flex flex-col items-center gap-5 px-6 pt-28 text-center">
          <ShoppingBag size={40} strokeWidth={1.25} className="text-sand" />
          <p className="text-muted">{t('cart.empty')}</p>
          <Link to=".." className="rounded-full bg-brand px-6 py-3 text-sm font-medium text-on-brand">
            {t('cart.browse')}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-dvh pb-10">
      <Header title={t('cart.title')} backTo=".." />
      <main className="mx-auto max-w-2xl px-4">
        <ul className="divide-y divide-line">
          {lines.map((l, i) => {
            const p = productsById.get(l.product_id)
            const quoted = quote?.lines[i]
            const optionNames = quoted
              ? quoted.options.map((o) => pick({ en: o.name_en, km: o.name_km, zh: o.name_zh }))
              : p?.option_groups.flatMap((g) => g.options.filter((o) => l.option_ids.includes(o.id)).map((o) => pick(o.name))) ?? []
            const hasProblem = problem?.line === i
            const name = p ? pick(p.name) : '—'
            return (
              <li key={l.key} className="flex gap-3 py-4">
                <ProductImage
                  src={p?.image_url}
                  alt={name}
                  categorySlug={categoriesById.get(p?.category_id)?.slug}
                  className="size-16 shrink-0 rounded-lg"
                  iconSize={22}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium leading-snug">{name}</span>
                    <span className="shrink-0 font-semibold tabular-nums">
                      {quoted ? formatPrice(quoted.line_total_usd_cents, settings).primary : ''}
                    </span>
                  </div>
                  {optionNames.length > 0 && <p className="mt-0.5 text-sm text-muted">{optionNames.join(' · ')}</p>}
                  {l.special_instructions && <p className="mt-0.5 text-sm italic text-muted">“{l.special_instructions}”</p>}
                  {hasProblem && (
                    <p className="mt-1 text-sm font-medium text-danger" role="alert">
                      {t('cart.lineProblem')}: {problem.message}
                    </p>
                  )}
                  <div className="mt-2 flex items-center justify-between">
                    <Stepper value={l.quantity} onChange={(q) => setQty(l.key, q)} size="sm" />
                    <button
                      onClick={() => setQty(l.key, 0)}
                      className="grid size-9 place-items-center rounded-full text-muted hover:text-danger"
                      aria-label={t('cart.remove', { name })}
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>

        <Link to=".." className="mt-2 inline-flex items-center gap-2 py-3 text-sm font-medium text-accent">
          <Plus size={16} /> {t('cart.addMore')}
        </Link>

        <section className="mt-4 rounded-2xl border border-line bg-surface p-5" aria-live="polite">
          {problem && problem.line === null && <p className="mb-3 text-sm text-danger">{problem.message}</p>}
          <div className="flex items-baseline justify-between">
            <span className="text-muted">{t('cart.subtotal')}</span>
            {quote ? (
              <span className="text-right">
                <span className="block text-xl font-semibold tabular-nums">
                  {settings.display_currency === 'KHR' ? formatKHR(quote.subtotal_khr) : formatUSD(quote.subtotal_usd_cents)}
                </span>
                {settings.show_secondary_currency && (
                  <span className="block text-sm text-muted tabular-nums">
                    {settings.display_currency === 'KHR' ? formatUSD(quote.subtotal_usd_cents) : formatKHR(quote.subtotal_khr)}
                  </span>
                )}
              </span>
            ) : (
              <span className="text-sm text-muted">{loading ? t('cart.priceCheck') : '—'}</span>
            )}
          </div>
          {quote && (
            <p className="mt-3 flex items-center gap-1.5 text-sm text-muted">
              <Clock size={14} /> {t('cart.estimate', { n: quote.estimated_minutes })}
            </p>
          )}
          <p className="mt-3 text-xs text-muted">{t('cart.priceNote')}</p>
        </section>
      </main>
    </div>
  )
}
