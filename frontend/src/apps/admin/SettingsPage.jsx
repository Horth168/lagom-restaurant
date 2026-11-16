import { useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { api } from '../../lib/api'
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
  ['telegram_notify_shifts', 'admin.settings.tgShifts'],
  ['telegram_notify_service', 'admin.settings.tgService'],
  ['telegram_notify_reviews', 'admin.settings.tgReviews'],
  ['backup_reminder', 'admin.settings.tgBackup'],
]

const PHOTO_LABEL = { r2: 'admin.settings.photosR2', database: 'admin.settings.photosDb', disk: 'admin.settings.photosDisk' }

export default function SettingsPage() {
  const { t, pick } = useI18n()
  const { staffApi, token } = useStaff()
  const [categories, setCategories] = useState([])
  const toast = useToast()
  const [data, setData] = useState(null)
  const [f, setF] = useState(null)

  useEffect(() => {
    staffApi('/api/settings').then((d) => {
      setData(d)
      setF(d.settings)
    })
    api('/api/public/menu').then((m) => setCategories(m.categories)).catch(() => {})
  }, [staffApi])

  async function save() {
    const body = {
      restaurant_name: f.restaurant_name, khr_per_usd: String(f.khr_per_usd), display_currency: f.display_currency,
      show_secondary_currency: f.show_secondary_currency, accepted_payment_currencies: f.accepted_payment_currencies,
      receipt_footer: f.receipt_footer, inventory_deduct_on: f.inventory_deduct_on,
      ...Object.fromEntries(ALERTS.map(([k]) => [k, f[k]])), daily_summary_time: f.daily_summary_time,
      auto_sold_out: f.auto_sold_out, loyalty_enabled: f.loyalty_enabled,
      loyalty_stamps_needed: Number(f.loyalty_stamps_needed), loyalty_category_ids: f.loyalty_category_ids,
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

  async function downloadBackup() {
    const res = await fetch(`${import.meta.env.VITE_API_URL || ''}/api/admin/backup.xlsx`, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) return toast(t('admin.failed'), 'bad')
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = (res.headers.get('content-disposition') || '').match(/filename="(.+)"/)?.[1] || 'lagom-backup.xlsx'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  }

  if (!f) return <Skeleton className="h-96" />
  const toggleCat = (id) => setF({ ...f, loyalty_category_ids: f.loyalty_category_ids.includes(id) ? f.loyalty_category_ids.filter((x) => x !== id) : [...f.loyalty_category_ids, id] })
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
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={!!f.auto_sold_out} onChange={(e) => setF({ ...f, auto_sold_out: e.target.checked })} />
              <span>{t('admin.settings.autoSoldOut')}<span className="block text-xs text-muted">{t('admin.settings.autoSoldOutHint')}</span></span>
            </label>
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
        <Card title={t('loyalty.title')}>
          <p className="text-sm text-muted">{t('loyalty.hint')}</p>
          <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={!!f.loyalty_enabled} onChange={(e) => setF({ ...f, loyalty_enabled: e.target.checked })} /> {t('loyalty.enable')}</label>
          <div className="mt-4">
            <Field label={t('loyalty.needed')} hint={t('loyalty.neededHint', { n: f.loyalty_stamps_needed })}>
              <input type="number" min={2} max={50} className={`${inputBase} w-28`} value={f.loyalty_stamps_needed} disabled={!f.loyalty_enabled}
                onChange={(e) => setF({ ...f, loyalty_stamps_needed: e.target.value })} />
            </Field>
          </div>
          <div className="mt-4">
            <span className="text-sm font-medium">{t('loyalty.categories')}</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {categories.map((c) => {
                const on = f.loyalty_category_ids.includes(c.id)
                return (
                  <button key={c.id} type="button" aria-pressed={on} disabled={!f.loyalty_enabled} onClick={() => toggleCat(c.id)}
                    className={`h-9 rounded-full px-3 text-sm disabled:opacity-50 ${on ? 'bg-brand text-on-brand' : 'border border-line'}`}>{pick(c.name)}</button>
                )
              })}
            </div>
          </div>
        </Card>
        <Card title={t('backup.title')}>
          <p className="text-sm text-muted">{t('backup.hint')}</p>
          <Button className="mt-4" onClick={downloadBackup}><Download size={16} /> {t('backup.download')}</Button>
          <p className="mt-3 text-xs text-muted">{t('backup.safe')}</p>
        </Card>
        <Card title={t('admin.settings.integrations')} className="lg:col-span-2">
          <ul className="grid gap-3 text-sm sm:grid-cols-2">
            {[['khqr_configured', 'admin.settings.khqr'], ['payment_listener_configured', 'admin.pay.listener'], ['telegram_configured', 'admin.settings.telegram']].map(([k, label]) => (
              <li key={k} className="flex items-center justify-between rounded-lg border border-line p-3">
                {t(label)} <Badge tone={i[k] ? 'good' : 'neutral'}>{i[k] ? t('admin.settings.on') : t('admin.pay.notSetUp')}</Badge>
              </li>
            ))}
            <li className="flex items-center justify-between rounded-lg border border-line p-3">
              {t('admin.settings.photos')} <Badge tone={i.photo_storage === 'disk' ? 'warn' : 'good'}>{t(PHOTO_LABEL[i.photo_storage] || 'admin.settings.photosDisk')}</Badge>
            </li>
          </ul>
          <p className="mt-3 text-xs text-muted">{t('admin.settings.integrationsHint')}</p>
        </Card>
      </div>
      <div className="mt-6"><Button variant="primary" size="lg" onClick={save}>{t('admin.save')}</Button></div>
    </>
  )
}
