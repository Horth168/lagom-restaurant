/* Pickup ordering inside Telegram (the LAGOM Mini App, opened from the bot's menu button).
 * Telegram gives this page a signed login text (initData). We send it to our server,
 * which checks the signature with the bot token before opening a pickup session.
 * The same menu, cart, KHQR/cash payment and live tracking as the table app are used.
 */
import { useEffect, useState } from 'react'
import { Mark } from '../../components/Logo'
import { api } from '../../lib/api'
import { useI18n } from '../../i18n'
import { Centered, Gate } from './CustomerApp'
import { CustomerProvider } from './CustomerContext'

const SDK = 'https://telegram.org/js/telegram-web-app.js'

function loadTelegram() {
  if (window.Telegram?.WebApp) return Promise.resolve(window.Telegram.WebApp)
  return new Promise((resolve) => {
    const s = document.createElement('script')
    s.src = SDK
    s.async = true
    s.onload = () => resolve(window.Telegram?.WebApp ?? null)
    s.onerror = () => resolve(null)
    document.head.appendChild(s)
  })
}

// Telegram's login is checked again on every open, so a saved session is only reused by the server
const openTelegramSession = (initData) => (_previous, language) =>
  api('/api/public/telegram/session', { method: 'POST', body: { init_data: initData, language } })

export default function TelegramApp() {
  const { t } = useI18n()
  const [state, setState] = useState({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    loadTelegram().then((app) => {
      if (cancelled) return
      if (!app?.initData) return setState({ status: 'outside' })
      app.ready()
      app.expand()
      setState({ status: 'ready', open: openTelegramSession(app.initData) })
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (state.status === 'loading') return <div className="min-h-dvh" aria-busy="true" />
  if (state.status === 'outside') {
    return (
      <Centered>
        <Mark size={56} className="text-brand" />
        <p className="max-w-xs text-center text-ink">{t('entry.telegram')}</p>
      </Centered>
    )
  }
  return (
    <CustomerProvider storageId="telegram" openSession={state.open}>
      <Gate />
    </CustomerProvider>
  )
}
