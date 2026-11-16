/* Everything the customer app shares: table session, menu, settings and cart.
 * The table session token is private to this phone and kept in localStorage so a
 * refresh or re-scan recovers the same session.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../../lib/api'
import { addLine, setQuantity } from '../../lib/cartMath'
import { useI18n } from '../../i18n'

const Ctx = createContext(null)

const read = (key, fallback) => {
  try {
    const v = localStorage.getItem(key)
    return v ? JSON.parse(v) : fallback
  } catch {
    return fallback
  }
}
const write = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage full or blocked: the app still works for this visit */
  }
}

export function CustomerProvider({ qrToken, children }) {
  const { lang } = useI18n()
  const sessionKey = `lagom.session.${qrToken}`
  const cartKey = `lagom.cart.${qrToken}`

  const [session, setSession] = useState(null)
  const [menu, setMenu] = useState(null)
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState(null) // 'invalid' | 'offline'
  const [lines, setLines] = useState(() => read(cartKey, []))
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setError(null)
    const previous = read(sessionKey, null)
    Promise.all([
      api(`/api/public/tables/${encodeURIComponent(qrToken)}/session`, {
        method: 'POST',
        body: { previous_session_token: previous?.session_token ?? null, language: lang },
      }),
      api('/api/public/menu'),
      api('/api/settings/public'),
    ])
      .then(([s, m, st]) => {
        if (cancelled) return
        write(sessionKey, s)
        setSession(s)
        setMenu(m)
        setSettings(st)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e instanceof ApiError && e.status === 404 ? 'invalid' : 'offline')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- language changes must not open a new session
  }, [qrToken, sessionKey, attempt])

  useEffect(() => write(cartKey, lines), [cartKey, lines])

  const add = useCallback((line) => setLines((ls) => addLine(ls, line)), [])
  const setQty = useCallback((key, q) => setLines((ls) => setQuantity(ls, key, q)), [])
  const clear = useCallback(() => setLines([]), [])
  const retry = useCallback(() => setAttempt((a) => a + 1), [])

  const value = useMemo(() => {
    const productsById = new Map((menu?.products ?? []).map((p) => [p.id, p]))
    const categoriesById = new Map((menu?.categories ?? []).map((c) => [c.id, c]))
    return {
      qrToken, session, menu, settings, error, retry,
      productsById, categoriesById,
      lines, add, setQty, clear,
    }
  }, [qrToken, session, menu, settings, error, retry, lines, add, setQty, clear])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useCustomer() {
  return useContext(Ctx)
}
