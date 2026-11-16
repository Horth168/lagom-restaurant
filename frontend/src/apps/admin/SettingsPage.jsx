import { useEffect, useState } from 'react'
import { Badge, Button, Card, Field, inputBase, inputCls, Skeleton, useToast } from '../../components/ui'
import { useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const ALERTS = [
  ['telegram_notify_new_orders', 'admin.settings.tgNew'],
  ['telegram_notify_failed_payments', 'admin.settings.tgFailed'],
  ['telegram_notify_cancellations', 'admin.settings.tgCancel'],
  ['telegram_notify_low_stock', 'admin.settings.tgLow'],
  ['telegram_daily_summary', 'admin.settings.tgDaily'],
]

export default function SettingsPage() {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [f, setF] = useState(null)

  useEffect(() => {
    staffApi('/api/settings').then((d) => {
      setData(d)
      setF(d.settings)
    })
  }, [staffApi])

  async function save() {
    const body = {
      restaurant_name: f.restaurant_name, khr_per_usd: String(f.khr_per_usd), display_currency: f.display_currency,
      show_secondary_currency: f.show_secondary_currency, accepted_payment_currencies: f.accepted_payment_currencies,
      receipt_footer: f.receipt_footer, inventory_deduct_on: f.inventory_deduct_on,
      ...Object.fromEntries(ALERTS.map(([k]) => [k, f[k]])), daily_summary_time: f.daily_summary_time,
    }
    try {
      setF(await staffApi('/api/settings', { method: 'PATCH', body }))
      toast(t('admin.saved'))
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  async function sendTest() {
    try {
      await staffApi('/api/settings/telegram/test', { method: 'POST' })
      toast(t('admin.settings.tgSent'))
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  if (!f) return <Skeleton className="h-96" />
  const accepts = (c) => f.accepted_payment_currencies.includes(c)
  const toggleCurrency = (c) =>
    setF({ ...f, accepted_payment_currencies: accepts(c) ? f.accepted_payment_currencies.filter((x) => x !== c) : [...f.accepted_payment_currencies, c] })
  const i = data.integrations

  return (
    <>
      <PageTitle title={t('admin.nav.settings')} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t('admin.settings.money')}>
          <div className="space-y-4">
            <Field label={t('admin.settings.rate')} hint={t('admin.settings.rateHint')}>
              <input className={inputCls} inputMode="decimal" value={f.khr_per_usd} onChange={(e) => setF({ ...f, khr_per_usd: e.target.value })} />
            </Field>
            <Field label={t('admin.settings.display')}>
              <select className={inputCls} value={f.display_currency} onChange={(e) => setF({ ...f, display_currency: e.target.value })}>
                <option value="USD">USD ($)</option>
                <option value="KHR">KHR (៛)</option>
              </select>
            </Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.show_secondary_currency} onChange={(e) => setF({ ...f, show_secondary_currency: e.target.checked })} /> {t('admin.settings.showBoth')}</label>
            <div>
              <span className="text-sm font-medium">{t('admin.settings.payIn')}</span>
              <div className="mt-2 flex gap-4 text-sm">
                {['USD', 'KHR'].map((c) => (
                  <label key={c} className="flex items-center gap-2"><input type="checkbox" checked={accepts(c)} onChange={() => toggleCurrency(c)} disabled={accepts(c) && f.accepted_payment_currencies.length === 1} /> {c}</label>
                ))}
              </div>
            </div>
          </div>
        </Card>
        <Card title={t('admin.settings.general')}>
          <div className="space-y-4">
            <Field label={t('admin.settings.name')}><input className={inputCls} value={f.restaurant_name} onChange={(e) => setF({ ...f, restaurant_name: e.target.value })} /></Field>
            <Field label={t('admin.settings.footer')}><input className={inputCls} value={f.receipt_footer} onChange={(e) => setF({ ...f, receipt_footer: e.target.value })} /></Field>
            <Field label={t('admin.settings.deduct')} hint={t('admin.settings.deductHint')}>
              <select className={inputCls} value={f.inventory_deduct_on} onChange={(e) => setF({ ...f, inventory_deduct_on: e.target.value })}>
                <option value="PAID">{t('admin.settings.deductPaid')}</option>
                <option value="READY">{t('admin.settings.deductReady')}</option>
              </select>
            </Field>
          </div>
        </Card>
        <Card title={t('admin.settings.tgTitle')} className="lg:col-span-2">
          <p className="text-sm text-muted">{t('admin.settings.tgHint')}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {ALERTS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!!f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} /> {t(label)}
              </label>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-end gap-4">
            <Field label={t('admin.settings.tgTime')}>
              <input type="time" className={`${inputBase} w-36`} value={f.daily_summary_time} disabled={!f.telegram_daily_summary}
                onChange={(e) => setF({ ...f, daily_summary_time: e.target.value })} />
            </Field>
            <Button onClick={sendTest} disabled={!i.telegram_configured}>{t('admin.settings.tgTest')}</Button>
          </div>
          {!i.telegram_configured && <p className="mt-3 text-xs text-muted">{t('admin.settings.tgNotSetUp')}</p>}
        </Card>
        <Card title={t('admin.settings.integrations')} className="lg:col-span-2">
          <ul className="grid gap-3 text-sm sm:grid-cols-2">
            {[['khqr_configured', 'admin.settings.khqr'], ['payment_listener_configured', 'admin.pay.listener'], ['telegram_configured', 'admin.settings.telegram'], ['r2_configured', 'admin.settings.r2']].map(([k, label]) => (
              <li key={k} className="flex items-center justify-between rounded-lg border border-line p-3">
                {t(label)} <Badge tone={i[k] ? 'good' : 'neutral'}>{i[k] ? t('admin.settings.on') : t('admin.pay.notSetUp')}</Badge>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted">{t('admin.settings.integrationsHint')}</p>
        </Card>
      </div>
      <div className="mt-6"><Button variant="primary" size="lg" onClick={save}>{t('admin.save')}</Button></div>
    </>
  )
}
