/* Timed deals: e.g. "Happy hour · Coffee −20% · Mon–Fri 14:00–17:00". Applied by the server. */
import { useCallback, useEffect, useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { Sheet } from '../../components/Sheet'
import { Badge, Button, Card, Field, inputBase, inputCls, Skeleton, useToast } from '../../components/ui'
import { useI18n } from '../../i18n'
import { api } from '../../lib/api'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const DAYS = ['0', '1', '2', '3', '4', '5', '6'] // Monday … Sunday
const EMPTY = { name: '', percent: 20, category_id: null, product_id: null, weekdays: '0123456', start_time: '14:00', end_time: '17:00', is_active: true }

export default function Deals() {
  const { t, pick } = useI18n()
  const { staffApi, can } = useStaff()
  const toast = useToast()
  const [deals, setDeals] = useState(null)
  const [menu, setMenu] = useState(null)
  const [edit, setEdit] = useState(null)
  const editable = can('menu.edit')

  const load = useCallback(() => staffApi('/api/admin/deals').then(setDeals), [staffApi])
  useEffect(() => {
    load()
    api('/api/public/menu').then(setMenu)
  }, [load])

  async function save() {
    const body = { ...edit, percent: Number(edit.percent) }
    try {
      if (edit.id) await staffApi(`/api/admin/deals/${edit.id}`, { method: 'PUT', body })
      else await staffApi('/api/admin/deals', { method: 'POST', body })
      setEdit(null)
      toast(t('admin.saved'))
      load()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  async function remove(d) {
    if (!window.confirm(t('deals.confirmDelete', { name: d.name }))) return
    await staffApi(`/api/admin/deals/${d.id}`, { method: 'DELETE' })
    load()
  }

  const target = (d) => {
    if (d.product_id) return pick(menu?.products.find((p) => p.id === d.product_id)?.name ?? { en: '—' })
    if (d.category_id) return pick(menu?.categories.find((c) => c.id === d.category_id)?.name ?? { en: '—' })
    return t('deals.wholeMenu')
  }
  const dayNames = (w) => (w.length === 7 ? t('deals.everyDay') : [...w].map((d) => t(`day.${d}`)).join(' '))

  if (!deals) return <Skeleton className="h-64" />
  return (
    <>
      <PageTitle title={t('admin.nav.deals')}>
        {editable && <Button variant="primary" onClick={() => setEdit({ ...EMPTY })}><Plus size={16} /> {t('deals.new')}</Button>}
      </PageTitle>
      <p className="mb-4 max-w-2xl text-sm text-muted">{t('deals.hint')}</p>
      <Card>
        {deals.length === 0 ? (
          <p className="py-8 text-center text-muted">{t('deals.none')}</p>
        ) : (
          <ul className="divide-y divide-line">
            {deals.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 py-3">
                <span className="text-2xl font-semibold tabular-nums text-series-2">−{d.percent}%</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{d.name}</span>
                  <span className="block text-sm text-muted">{target(d)} · {dayNames(d.weekdays)} · {d.start_time}–{d.end_time}</span>
                </span>
                {!d.is_active ? <Badge>{t('deals.off')}</Badge> : d.running_now ? <Badge tone="good">{t('deals.now')}</Badge> : <Badge tone="info">{t('deals.scheduled')}</Badge>}
                {editable && (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => setEdit({ ...d })} aria-label={t('deals.edit')}><Pencil size={15} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => remove(d)} aria-label={t('deals.delete')}><Trash2 size={15} /></Button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Sheet open={!!edit} onClose={() => setEdit(null)} label={t('deals.new')}>
        {edit && (
          <div className="space-y-4 p-6">
            <h2 className="font-display text-2xl">{edit.id ? t('deals.edit') : t('deals.new')}</h2>
            <Field label={t('deals.name')}><input className={inputCls} value={edit.name} maxLength={80} placeholder="Happy hour" onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label={t('deals.percent')}>
              <input className={`${inputBase} w-28`} type="number" min={1} max={90} value={edit.percent} onChange={(e) => setEdit({ ...edit, percent: e.target.value })} />
            </Field>
            <Field label={t('deals.appliesTo')}>
              <select className={inputCls}
                value={edit.product_id ? `p${edit.product_id}` : edit.category_id ? `c${edit.category_id}` : ''}
                onChange={(e) => {
                  const v = e.target.value
                  setEdit({ ...edit, category_id: v.startsWith('c') ? Number(v.slice(1)) : null, product_id: v.startsWith('p') ? Number(v.slice(1)) : null })
                }}>
                <option value="">{t('deals.wholeMenu')}</option>
                <optgroup label={t('deals.categories')}>
                  {menu?.categories.map((c) => <option key={c.id} value={`c${c.id}`}>{pick(c.name)}</option>)}
                </optgroup>
                <optgroup label={t('deals.dishes')}>
                  {menu?.products.map((p) => <option key={p.id} value={`p${p.id}`}>{pick(p.name)}</option>)}
                </optgroup>
              </select>
            </Field>
            <div>
              <span className="text-sm font-medium">{t('deals.days')}</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {DAYS.map((d) => {
                  const on = edit.weekdays.includes(d)
                  return (
                    <button key={d} type="button" aria-pressed={on}
                      onClick={() => setEdit({ ...edit, weekdays: on ? edit.weekdays.replace(d, '') : [...edit.weekdays, d].sort().join('') })}
                      className={`h-9 rounded-full px-3 text-sm ${on ? 'bg-brand text-on-brand' : 'border border-line'}`}>{t(`day.${d}`)}</button>
                  )
                })}
              </div>
            </div>
            <div className="flex gap-4">
              <Field label={t('deals.from')}><input type="time" className={`${inputBase} w-32`} value={edit.start_time} onChange={(e) => setEdit({ ...edit, start_time: e.target.value })} /></Field>
              <Field label={t('deals.to')}><input type="time" className={`${inputBase} w-32`} value={edit.end_time} onChange={(e) => setEdit({ ...edit, end_time: e.target.value })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> {t('deals.active')}</label>
            <Button variant="primary" size="lg" className="w-full" onClick={save} disabled={!edit.name.trim() || !edit.weekdays}>{t('admin.save')}</Button>
          </div>
        )}
      </Sheet>
    </>
  )
}
