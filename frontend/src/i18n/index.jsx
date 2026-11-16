/* Central translations. Every visible word comes from en.json / km.json / zh.json.
 * Usage: const { t, lang, pick } = useI18n();  t('cart.items', { n: 3 });  pick(product.name)
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import en from './en.json'
import km from './km.json'
import zh from './zh.json'

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'km', label: 'ខ្មែរ' },
  { code: 'zh', label: '中文' },
]
const DICTS = { en, km, zh }
const LOCALES = { en: 'en-GB', km: 'km-KH', zh: 'zh-CN' }

/** Date/time format of the language the app is showing (dates follow the app, not the browser). */
export function appLocale() {
  return LOCALES[typeof document !== 'undefined' ? document.documentElement.lang : 'en'] || 'en-GB'
}
const STORAGE_KEY = 'lagom.lang'

function initialLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && DICTS[saved]) return saved
  } catch {
    /* storage blocked */
  }
  const nav = (typeof navigator !== 'undefined' && navigator.language) || 'en'
  if (nav.startsWith('km')) return 'km'
  if (nav.startsWith('zh')) return 'zh'
  return 'en'
}

export function translate(lang, key, vars) {
  let s = DICTS[lang]?.[key] ?? DICTS.en[key] ?? key
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v))
  return s
}

const I18nContext = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(initialLang)

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLang = useCallback((code) => {
    if (!DICTS[code]) return
    setLangState(code)
    try {
      localStorage.setItem(STORAGE_KEY, code)
    } catch {
      /* ignore */
    }
  }, [])

  const value = useMemo(
    () => ({
      lang,
      setLang,
      t: (key, vars) => translate(lang, key, vars),
      // Pick the right language from a {en, km, zh} object coming from the API
      pick: (obj) => (obj ? obj[lang] || obj.en || '' : ''),
    }),
    [lang, setLang],
  )
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  return useContext(I18nContext)
}
