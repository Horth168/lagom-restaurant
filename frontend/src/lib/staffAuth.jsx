/* Staff sign-in shared by the kitchen display, POS and admin.
 * The login token is kept in this device's storage; permissions are always checked again by the server.
 */
import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, ApiError } from './api'
import { useI18n } from '../i18n'

const KEY = 'lagom.staff'
const Ctx = createContext(null)

function load() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (v?.token && v?.expires_at > Date.now()) return v
  } catch {
    /* ignore */
  }
  return null
}

export function StaffAuthProvider({ children }) {
  const [auth, setAuth] = useState(load)
  const { setLang } = useI18n()

  const login = useCallback(async (email, password) => {
    const r = await api('/api/auth/login', { method: 'POST', body: { email, password } })
    const value = { token: r.access_token, user: r.user, expires_at: Date.now() + r.expires_in_minutes * 60000 }
    try {
      localStorage.setItem(KEY, JSON.stringify(value))
    } catch {
      /* ignore */
    }
    setAuth(value)
    if (value.user.preferred_language) setLang(value.user.preferred_language) // open in their language
    return value.user
  }, [setLang])

  const logout = useCallback(() => {
    try {
      localStorage.removeItem(KEY)
    } catch {
      /* ignore */
    }
    setAuth(null)
  }, [])

  // API call with the staff token; signs out automatically if the server says the login is no longer valid
  const staffApi = useCallback(
    async (path, opts = {}) => {
      try {
        return await api(path, { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${auth?.token}` } })
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) logout()
        throw e
      }
    },
    [auth, logout],
  )

  // Remember a language change on the staff account too
  const saveLanguage = useCallback(
    async (code) => {
      setLang(code)
      if (!auth?.token) return
      try {
        const user = await api('/api/auth/me', { method: 'PATCH', body: { preferred_language: code }, headers: { Authorization: `Bearer ${auth.token}` } })
        const next = { ...auth, user }
        localStorage.setItem(KEY, JSON.stringify(next))
        setAuth(next)
      } catch {
        /* the screen language still changed */
      }
    },
    [auth, setLang],
  )

  const value = useMemo(
    () => ({
      saveLanguage,
      user: auth?.user ?? null,
      token: auth?.token ?? null,
      can: (perm) => !!auth?.user?.permissions?.includes(perm),
      login,
      logout,
      staffApi,
    }),
    [auth, login, logout, staffApi, saveLanguage],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStaff() {
  return useContext(Ctx)
}

export function RequireStaff({ children }) {
  const { user } = useStaff()
  const location = useLocation()
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  return children
}
