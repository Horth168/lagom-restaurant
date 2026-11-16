/* View-only menu (lagom-web…/menu): share on Facebook, Google Maps, Instagram.
 * People browse dishes, photos and prices; ordering happens at the table (QR) or in Telegram. */
import { useEffect, useMemo, useState } from 'react'
import { Globe, QrCode } from 'lucide-react'
import { LogoHorizontal, Mark } from '../../components/Logo'
import { Price } from '../../components/Price'
import { ProductImage } from '../../components/ProductImage'
import { LANGUAGES, useI18n } from '../../i18n'
import { api } from '../../lib/api'
import { dealPrice } from '../../lib/cartMath'
import { formatPrice } from '../../lib/money'

export default function BrowseMenu() {
  const { t, pick, lang, setLang } = useI18n()
  const [menu, setMenu] = useState(null)
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState(false)
  const [cat, setCat] = useState('all')

  useEffect(() => {
    Promise.all([api('/api/public/menu'), api('/api/settings/public')])
      .then(([m, s]) => { setMenu(m); setSettings(s) })
      .catch(() => setError(true))
  }, [])

  const groups = useMemo(() => {
    if (!menu) return []
    return menu.categories
      .filter((c) => cat === 'all' || c.id === cat)
      .map((c) => ({ cat: c, items: menu.products.filter((p) => p.category_id === c.id) }))
      .filter((g) => g.items.length)
  }, [menu, cat])

  const nextLang = LANGUAGES[(LANGUAGES.findIndex((l) => l.code === lang) + 1) % LANGUAGES.length]

  if (error) return <div className="grid min-h-dvh place-items-center p-6 text-center text-muted">{t('entry.offline')}</div>
  if (!menu) return <div className="grid min-h-dvh place-items-center"><Mark size={56} className="text-brand" /></div>

  return (
    <div className="min-h-dvh pb-16">
      <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-3 px-4">
          <LogoHorizontal height={26} className="text-brand" />
          <button onClick={() => setLang(nextLang.code)} className="ml-auto flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm hover:bg-surface-2">
            <Globe size={16} /> {nextLang.label}
          </button>
        </div>
        <nav className="no-scrollbar mx-auto flex max-w-3xl gap-2 overflow-x-auto px-4 pb-3">
          {[{ id: 'all', name: { en: t('pos.all') } }, ...menu.categories].map((c) => (
            <button key={c.id} onClick={() => setCat(c.id)} aria-pressed={cat === c.id}
              className={`shrink-0 rounded-full px-4 py-2 text-sm ${cat === c.id ? 'bg-brand text-on-brand' : 'border border-line bg-surface'}`}>
              {pick(c.name)}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-3xl px-4">
        <p className="mt-4 flex items-center gap-2 rounded-xl bg-surface-2 p-3 text-sm">
          <QrCode size={18} className="shrink-0 text-accent" /> {t('browse.howToOrder')}
        </p>
        {groups.map(({ cat: c, items }) => (
          <section key={c.id} className="mt-8">
            <h2 className="font-display text-2xl">{pick(c.name)}</h2>
            <ul className="mt-3 grid gap-4 sm:grid-cols-2">
              {items.map((p) => (
                <li key={p.id} className={`flex gap-4 rounded-2xl border border-line bg-surface p-3 ${p.is_available ? '' : 'opacity-60'}`}>
                  <ProductImage src={p.image_url} alt={pick(p.name)} categorySlug={c.slug} className="size-24 shrink-0 rounded-xl" />
                  <div className="min-w-0">
                    <h3 className="font-medium leading-snug">{pick(p.name)}</h3>
                    {p.deal && <span className="mt-1 inline-block rounded-full bg-series-2/15 px-2 py-0.5 text-[11px] font-semibold text-series-2">{p.deal.name} · −{p.deal.percent}%</span>}
                    <p className="mt-1 line-clamp-2 text-sm text-muted">{pick(p.description)}</p>
                    <div className="mt-1.5 text-[15px] font-semibold">
                      {p.is_available ? (
                        <>
                          <Price cents={dealPrice(p.price_usd_cents, p.deal?.percent)} settings={settings} inline secondaryClassName="text-xs" />
                          {p.deal && <s className="ml-2 text-sm font-normal text-muted">{formatPrice(p.price_usd_cents, settings).primary}</s>}
                        </>
                      ) : <span className="text-muted">{t('menu.soldOut')}</span>}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
        <p className="mt-12 text-center text-[11px] font-semibold uppercase tracking-[0.3em] text-gold">{t('brand.slogan')}</p>
      </main>
    </div>
  )
}
