import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Search, ShoppingBag, X } from 'lucide-react'
import { Price } from '../../components/Price'
import { ProductImage } from '../../components/ProductImage'
import { useI18n } from '../../i18n'
import { formatPrice } from '../../lib/money'
import { itemCount } from '../../lib/cartMath'
import { useCustomer } from './CustomerContext'
import { Header } from './Header'
import { ProductSheet } from './ProductSheet'

const normalize = (s) => s.toLocaleLowerCase().normalize('NFKD')

export function MenuPage() {
  const { t, pick } = useI18n()
  const { menu, settings, lines, categoriesById } = useCustomer()
  const [query, setQuery] = useState('')
  const [openProduct, setOpenProduct] = useState(null)
  const [activeCat, setActiveCat] = useState(menu.categories[0]?.id)
  const sectionRefs = useRef({})
  const tabRefs = useRef({})

  const byCategory = useMemo(() => {
    const map = new Map(menu.categories.map((c) => [c.id, []]))
    for (const p of menu.products) map.get(p.category_id)?.push(p)
    return map
  }, [menu])
  const visibleCategories = menu.categories.filter((c) => byCategory.get(c.id)?.length)
  const featured = menu.products.filter((p) => p.is_featured && p.is_available)

  const results = useMemo(() => {
    const q = normalize(query.trim())
    if (!q) return null
    // Search all three languages, so "latte", "ឡាតេ" and "拿铁" all work
    return menu.products.filter((p) =>
      [...Object.values(p.name), ...Object.values(p.description)].some((s) => normalize(s).includes(q)),
    )
  }, [query, menu])

  // Highlight the category tab for the section currently on screen
  useEffect(() => {
    if (results) return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActiveCat(Number(visible[0].target.dataset.cat))
      },
      { rootMargin: '-120px 0px -65% 0px' },
    )
    Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el))
    return () => observer.disconnect()
  }, [results, visibleCategories.length])

  useEffect(() => {
    tabRefs.current[activeCat]?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [activeCat])

  const jumpTo = (id) => {
    const el = sectionRefs.current[id]
    if (!el) return
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 112, behavior: 'smooth' })
  }

  const count = itemCount(lines)
  const promo = menu.promotions[0]

  return (
    <div className="min-h-dvh pb-28">
      <Header />
      <main className="mx-auto max-w-2xl">
        <div className="px-4 pt-4">
          <label className="flex h-11 items-center gap-2 rounded-xl border border-line bg-surface px-3 focus-within:border-accent">
            <Search size={18} className="text-muted" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('menu.search')}
              className="h-full flex-1 bg-transparent text-[16px] outline-none placeholder:text-muted"
              aria-label={t('menu.search')}
            />
            {query && (
              <button onClick={() => setQuery('')} aria-label={t('common.close')} className="text-muted">
                <X size={18} />
              </button>
            )}
          </label>
        </div>

        {results ? (
          <section className="px-4 pt-6">
            <h2 className="text-sm text-muted">{t('menu.searchResults', { q: query.trim() })}</h2>
            {results.length === 0 ? (
              <p className="py-16 text-center text-muted">{t('menu.noResults', { q: query.trim() })}</p>
            ) : (
              <ul className="mt-2 divide-y divide-line">
                {results.map((p) => (
                  <ProductRow key={p.id} product={p} slug={categoriesById.get(p.category_id)?.slug} onOpen={setOpenProduct} />
                ))}
              </ul>
            )}
          </section>
        ) : (
          <>
            {promo && (
              <section className="px-4 pt-5">
                <button
                  onClick={() => promo.product_id && setOpenProduct(menu.products.find((p) => p.id === promo.product_id))}
                  className="relative w-full overflow-hidden rounded-2xl bg-forest px-6 py-7 text-left text-cream"
                >
                  <span className="text-[11px] font-semibold uppercase tracking-[0.25em] text-gold">LAGOM</span>
                  <h2 className="mt-2 font-display text-[26px] leading-tight">{pick(promo.title)}</h2>
                  {pick(promo.subtitle) && <p className="mt-2 max-w-[85%] text-sm text-cream/80">{pick(promo.subtitle)}</p>}
                  <svg viewBox="0 0 64 64" className="pointer-events-none absolute -right-8 -bottom-10 size-44 opacity-20" aria-hidden="true">
                    <circle cx="32" cy="32" r="26" fill="none" stroke="#F3EBDD" strokeWidth="2" />
                    <circle cx="32" cy="32" r="18" fill="none" stroke="#C58B50" strokeWidth="2" />
                  </svg>
                </button>
              </section>
            )}

            {featured.length > 0 && (
              <section className="pt-7">
                <h2 className="px-4 font-display text-xl">{t('menu.featured')}</h2>
                <div className="no-scrollbar mt-3 flex snap-x snap-mandatory scroll-px-4 gap-3 overflow-x-auto px-4 pb-1">
                  {featured.map((p) => (
                    <button key={p.id} onClick={() => setOpenProduct(p)} className="w-40 shrink-0 snap-start text-left">
                      <ProductImage
                        src={p.image_url}
                        alt={pick(p.name)}
                        categorySlug={categoriesById.get(p.category_id)?.slug}
                        className="aspect-[4/5] w-full rounded-xl"
                        iconSize={34}
                      />
                      <div className="mt-2 line-clamp-2 text-[15px] font-medium leading-snug">{pick(p.name)}</div>
                      <div className="mt-0.5 text-sm font-semibold text-accent">{formatPrice(p.price_usd_cents, settings).primary}</div>
                    </button>
                  ))}
                </div>
              </section>
            )}

            <nav className="no-scrollbar sticky top-14 z-20 mt-6 flex gap-2 overflow-x-auto border-b border-line/70 bg-bg/95 px-4 py-2.5 backdrop-blur-md">
              {visibleCategories.map((c) => (
                <button
                  key={c.id}
                  ref={(el) => (tabRefs.current[c.id] = el)}
                  onClick={() => jumpTo(c.id)}
                  className={`shrink-0 rounded-full px-4 py-2 text-sm transition-colors ${
                    activeCat === c.id ? 'bg-brand text-on-brand' : 'bg-surface text-ink border border-line'
                  }`}
                  aria-current={activeCat === c.id ? 'true' : undefined}
                >
                  {pick(c.name)}
                </button>
              ))}
            </nav>

            {visibleCategories.map((c) => (
              <section key={c.id} data-cat={c.id} ref={(el) => (sectionRefs.current[c.id] = el)} className="px-4 pt-7">
                <h2 className="font-display text-2xl">{pick(c.name)}</h2>
                <ul className="mt-1 divide-y divide-line">
                  {byCategory.get(c.id).map((p) => (
                    <ProductRow key={p.id} product={p} slug={c.slug} onOpen={setOpenProduct} />
                  ))}
                </ul>
              </section>
            ))}
            <footer className="px-4 pt-14 pb-4 text-center text-[11px] uppercase tracking-[0.3em] text-muted">
              {t('brand.slogan')}
            </footer>
          </>
        )}
      </main>

      {count > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-30 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 bg-gradient-to-t from-bg via-bg/90 to-transparent">
          <Link
            to="cart"
            className="mx-auto flex h-14 max-w-2xl items-center gap-3 rounded-full bg-brand px-5 text-on-brand shadow-lg animate-fade-in"
          >
            <ShoppingBag size={20} />
            <span className="font-medium">{t('cart.view')}</span>
            <span className="ml-auto text-sm opacity-80">{count === 1 ? t('cart.item') : t('cart.items', { n: count })}</span>
          </Link>
        </div>
      )}

      <ProductSheet product={openProduct} onClose={() => setOpenProduct(null)} />
    </div>
  )
}

function ProductRow({ product: p, slug, onOpen }) {
  const { t, pick } = useI18n()
  const { settings } = useCustomer()
  const soldOut = !p.is_available
  return (
    <li>
      <button
        onClick={() => !soldOut && onOpen(p)}
        disabled={soldOut}
        className="flex w-full gap-4 py-4 text-left disabled:cursor-not-allowed"
        aria-label={soldOut ? `${pick(p.name)} · ${t('menu.soldOut')}` : pick(p.name)}
      >
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2">
            <span className={`text-[16px] font-medium leading-snug ${soldOut ? 'text-muted' : ''}`}>{pick(p.name)}</span>
          </div>
          {p.is_best_seller && !soldOut && (
            <span className="mt-1 w-fit text-[11px] font-semibold uppercase tracking-wider text-accent">{t('menu.bestSeller')}</span>
          )}
          <p className="mt-1 line-clamp-2 text-sm text-muted">{pick(p.description)}</p>
          <div className="mt-auto pt-2 text-[15px] font-semibold">
            {soldOut ? <span className="text-muted">{t('menu.soldOut')}</span> : <Price cents={p.price_usd_cents} settings={settings} inline secondaryClassName="text-xs" />}
          </div>
        </div>
        <div className="relative shrink-0">
          <ProductImage
            src={p.image_url}
            alt={pick(p.name)}
            categorySlug={slug}
            className={`size-24 rounded-xl ${soldOut ? 'opacity-50 grayscale' : ''}`}
          />
          {!soldOut && (
            <span className="absolute -right-1.5 -bottom-1.5 grid size-8 place-items-center rounded-full bg-brand text-on-brand shadow-md" aria-hidden="true">
              <Plus size={18} />
            </span>
          )}
        </div>
      </button>
    </li>
  )
}
