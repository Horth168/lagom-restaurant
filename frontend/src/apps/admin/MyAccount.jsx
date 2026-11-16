import { useState } from 'react'
import { Sheet } from '../../components/Sheet'
import { Button, Field, inputCls, ToastProvider, useToast } from '../../components/ui'
import { LANGUAGES, useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'

/** Change my language and my password. Changing the password signs out my other devices. */
export default function MyAccount({ onClose }) {
  return (
    <ToastProvider>
      <Account onClose={onClose} />
    </ToastProvider>
  )
}

function Account({ onClose }) {
  const { t, lang } = useI18n()
  const { user, staffApi, saveLanguage, logout } = useStaff()
  const toast = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')

  async function changePassword() {
    try {
      await staffApi('/api/auth/change-password', { method: 'POST', body: { current_password: current, new_password: next } })
      toast(t('acct.passwordChanged'))
      setTimeout(logout, 1500) // the old sign-in is no longer valid
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  return (
    <Sheet open onClose={onClose} label={t('acct.title')}>
      <div className="space-y-6 p-6">
        <div>
          <h2 className="font-display text-2xl">{user?.full_name}</h2>
          <p className="text-sm text-muted">{user?.email} · {t(`role.${user?.role}`)}</p>
        </div>
        <div>
          <h3 className="text-sm font-semibold">{t('lang.title')}</h3>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {LANGUAGES.map((l) => (
              <button key={l.code} lang={l.code} onClick={() => saveLanguage(l.code)}
                className={`h-11 rounded-lg border text-[15px] ${lang === l.code ? 'border-brand bg-brand text-on-brand' : 'border-line'}`}>{l.label}</button>
            ))}
          </div>
        </div>
        <div className="space-y-3">
          <h3 className="text-sm font-semibold">{t('acct.changePassword')}</h3>
          <Field label={t('acct.currentPassword')}><input type="password" autoComplete="current-password" className={inputCls} value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
          <Field label={t('acct.newPassword')} hint={t('staff.passwordRules')}><input type="password" autoComplete="new-password" className={inputCls} value={next} onChange={(e) => setNext(e.target.value)} /></Field>
          <Field label={t('acct.repeatPassword')}><input type="password" autoComplete="new-password" className={inputCls} value={repeat} onChange={(e) => setRepeat(e.target.value)} /></Field>
          {repeat && repeat !== next && <p className="text-sm text-danger">{t('acct.noMatch')}</p>}
          <Button variant="primary" className="w-full" disabled={!current || next.length < 10 || next !== repeat} onClick={changePassword}>{t('acct.changePassword')}</Button>
          <p className="text-xs text-muted">{t('acct.signOutOthers')}</p>
        </div>
      </div>
    </Sheet>
  )
}
