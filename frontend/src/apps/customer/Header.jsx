import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronLeft, Globe, MapPin, Moon, Receipt, Sun } from 'lucide-react'
import { LogoHorizontal } from '../../components/Logo'
import { Sheet } from '../../components/Sheet'
import { LANGUAGES, useI18n } from '../../i18n'
import { currentTheme, toggleTheme } from '../../lib/theme'
import { useCustomer } from './CustomerContext'
import { ServiceButton } from './ServiceButton'

export function Header({ title, backTo }) {
  const { t, lang, setLang } = useI18n()
  const { session } = useCustomer()
  const [langOpen, setLangOpen] = useState(false)
  const [theme, setTheme] = useState(currentTheme)

  return (
    <header className="sticky top-0 z-30 bg-bg/90 backdrop-blur-md border-b border-line/70">
      <div className="mx-auto flex h-14 max-w-2xl items-center gap-2 px-4">
        {backTo ? (
          <Link to={backTo} className="-ml-2 flex items-center gap-1 rounded-full py-2 pr-3 pl-1 text-ink" aria-label={t('common.back')}>
            <ChevronLeft size={22} />
            <span className="font-display text-lg">{title}</span>
          </Link>
        ) : (
          <LogoHorizontal height={26} className="text-brand" />
        )}
        <div className="ml-auto flex items-center gap-1">
          <span className="mr-1 inline-flex items-center gap-1 rounded-full bg-surface-2 px-3 py-1.5 text-xs font-medium text-ink">
            <MapPin size={13} className="text-accent" />
            {session?.pickup ? t('track.pickup') : session?.table.label}
          </span>
          <ServiceButton />
          {!backTo && (
            <Link to="orders" className="grid size-9 place-items-center rounded-full text-ink hover:bg-surface-2" aria-label={t('orders.title')}>
              <Receipt size={19} strokeWidth={1.75} />
            </Link>
          )}
          <button
            onClick={() => setLangOpen(true)}
            className="grid size-9 place-items-center rounded-full text-ink hover:bg-surface-2"
            aria-label={t('lang.title')}
          >
            <Globe size={19} strokeWidth={1.75} />
          </button>
          <button
            onClick={() => setTheme(toggleTheme())}
            className="grid size-9 place-items-center rounded-full text-ink hover:bg-surface-2"
            aria-label={t('theme.toggle')}
          >
            {theme === 'dark' ? <Sun size={19} strokeWidth={1.75} /> : <Moon size={19} strokeWidth={1.75} />}
          </button>
        </div>
      </div>

      <Sheet open={langOpen} onClose={() => setLangOpen(false)} label={t('lang.title')}>
        <div className="p-6 pt-7">
          <h2 className="font-display text-2xl">{t('lang.title')}</h2>
          <ul className="mt-4 divide-y divide-line">
            {LANGUAGES.map((l) => (
              <li key={l.code}>
                <button
                  lang={l.code}
                  onClick={() => {
                    setLang(l.code)
                    setLangOpen(false)
                  }}
                  className="flex w-full items-center justify-between py-4 text-left text-lg"
                >
                  {l.label}
                  {lang === l.code && <Check size={20} className="text-accent" />}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Sheet>
    </header>
  )
}
