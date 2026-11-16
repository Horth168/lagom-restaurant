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

/** Opens a table session from a printed table QR code. */
export const tableSession = (qrToken) => (previous, language) =>
  api(`/api/public/tables/${encodeURIComponent(qrToken)}/session`, {
    method: 'POST',
    body: { previous_session_token: previous?.session_token ?? null, language },
  })

/**
 * storageId keeps each table's (or Telegram's) cart separate on the phone.
 * openSession(previous, language) asks the server for this phone's private session.
 */
export function CustomerProvider({ storageId, openSession, children }) {
  const { lang } = useI18n()
  const sessionKey = `lagom.session.${storageId}`
  const cartKey = `lagom.cart.${storageId}`

  const [session, setSession] = useState(null)
  const [menu, setMenu] = useState(null)
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState(null) // 'invalid' | 'offline'
  const [lines, setLines] = useState(() => read(cartKey, []))
  const [attempt, setAttempt] = useState(0)
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))

  useEffect(() => {
    const up = () => {
      setOnline(true)
      setAttempt((a) => a + 1) // reconnect the table session
    }
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setError(null)
    const previous = read(sessionKey, null)
    Promise.all([
      openSession(previous, lang),
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
      .catch(async (e) => {
        if (cancelled) return
        if (e instanceof ApiError && [401, 404, 503].includes(e.status)) return setError(e.status === 404 ? 'invalid' : 'telegram')
        // No internet: show the menu saved on this phone (works if this table was opened before)
        if (previous) {
          try {
            const [m, st] = await Promise.all([api('/api/public/menu'), api('/api/settings/public')])
            if (cancelled) return
            setSession(previous)
            setMenu(m)
            setSettings(st)
            setOnline(false)
            return
          } catch {
            /* nothing saved yet */
          }
        }
        setError('offline')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- language changes must not open a new session
  }, [storageId, sessionKey, attempt])

  useEffect(() => write(cartKey, lines), [cartKey, lines])

  const add = useCallback((line) => setLines((ls) => addLine(ls, line)), [])
  const setQty = useCallback((key, q) => setLines((ls) => setQuantity(ls, key, q)), [])
  const clear = useCallback(() => setLines([]), [])
  const retry = useCallback(() => setAttempt((a) => a + 1), [])

  const token = session?.session_token
  // Sent with every customer request: proves which table session (phone) is asking
  const headers = useMemo(() => (token ? { 'X-Table-Session': token } : {}), [token])

  const value = useMemo(() => {
    const productsById = new Map((menu?.products ?? []).map((p) => [p.id, p]))
    const categoriesById = new Map((menu?.categories ?? []).map((c) => [c.id, c]))
    return {
      session, menu, settings, error, retry, online,
      productsById, categoriesById,
      lines, add, setQty, clear,
      headers,
    }
  }, [session, menu, settings, error, retry, online, lines, add, setQty, clear, headers])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useCustomer() {
  return useContext(Ctx)
}
