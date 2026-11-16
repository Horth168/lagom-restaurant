import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Mark, Wordmark } from '../../components/Logo'
import { useI18n } from '../../i18n'
import { ApiError } from '../../lib/api'
import { useStaff } from '../../lib/staffAuth'

export default function LoginPage() {
  const { t } = useI18n()
  const { user, login } = useStaff()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  // Only go back to a page inside this app (never to an outside address)
  const next = params.get('next')?.startsWith('/') && !params.get('next').startsWith('//') ? params.get('next') : '/kds'

  if (user) return <Navigate to={next} replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? t('login.tooMany') : err instanceof ApiError && err.status ? t('login.error') : t('entry.offline'))
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-forest px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-surface p-8 shadow-2xl">
        <div className="flex flex-col items-center gap-3 text-brand">
          <Mark size={48} />
          <Wordmark height={20} />
        </div>
        <h1 className="mt-6 text-center font-display text-2xl">{t('login.title')}</h1>
        <label className="mt-6 block">
          <span className="text-sm font-medium">{t('login.email')}</span>
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1.5 h-12 w-full rounded-xl border border-line bg-bg px-3 text-[16px] outline-none focus:border-accent"
          />
        </label>
        <label className="mt-4 block">
          <span className="text-sm font-medium">{t('login.password')}</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1.5 h-12 w-full rounded-xl border border-line bg-bg px-3 text-[16px] outline-none focus:border-accent"
          />
        </label>
        {error && <p className="mt-4 text-sm text-danger" role="alert">{error}</p>}
        <button disabled={busy} className="mt-6 h-12 w-full rounded-full bg-brand font-semibold text-on-brand disabled:opacity-50">
          {busy ? t('login.signingIn') : t('login.submit')}
        </button>
      </form>
    </main>
  )
}
