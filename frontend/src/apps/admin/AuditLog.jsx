/* Audit log: who did what, and when. Phones get easy-to-scan cards with tap-to-open details;
 * tablets and computers get a table. Search by action, person, IP or item number. */
import { useEffect, useState } from 'react'
import { ChevronDown, Search } from 'lucide-react'
import { Button, Card, inputBase, inputCls, Skeleton } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const AREAS = ['', 'auth.', 'staff.', 'order.', 'payment.', 'menu.', 'deal.', 'inventory.', 'finance.', 'shift.', 'settings.', 'table.', 'backup.']

/** "table.qr_rotated" -> "Table · QR rotated" */
export function humanAction(action) {
  const [area, ...rest] = String(action).split('.')
  const what = rest.join(' ').replaceAll('_', ' ')
  const cap = (x) => x.charAt(0).toUpperCase() + x.slice(1)
  return what ? `${cap(area)} · ${cap(what)}` : cap(area)
}

const detailText = (v) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))
const when = (at) => new Date(at)

function Details({ details }) {
  const entries = Object.entries(details || {})
  if (!entries.length) return null
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k.replaceAll('_', ' ')}</dt>
          <dd className="break-words font-mono text-ink">{detailText(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

function AuditCard({ e }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const has = Object.keys(e.details || {}).length > 0
  const d = when(e.at)
  return (
    <li className="rounded-xl border border-line bg-surface p-3.5">
      <div className="flex items-start justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-accent">
          {humanAction(e.action)}{e.entity_id && <span className="text-muted"> · #{e.entity_id}</span>}
        </span>
        <time className="shrink-0 text-xs tabular-nums text-muted" dateTime={e.at}>
          {d.toLocaleTimeString(appLocale(), { hour: '2-digit', minute: '2-digit' })}
        </time>
      </div>
      <div className="mt-1.5 font-medium">{e.user || t('audit.system')}</div>
      <div className="mt-0.5 text-xs text-muted">
        {d.toLocaleDateString(appLocale(), { day: 'numeric', month: 'short', year: 'numeric' })}
        {e.ip && <> · IP {e.ip}</>}
      </div>
      {has && (
        <>
          <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
            className="press mt-2 -ml-1 flex items-center gap-1 rounded-md px-1 py-1 text-xs font-medium text-accent">
            {t(open ? 'audit.hideDetails' : 'audit.viewDetails')}
            <ChevronDown size={14} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
          </button>
          {open && <div className="mt-1 animate-pop-in rounded-lg bg-surface-2 p-2.5"><Details details={e.details} /></div>}
        </>
      )}
    </li>
  )
}

export default function AuditLog() {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const [area, setArea] = useState('')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)

  // search after the person stops typing for a moment
  useEffect(() => {
    const id = setTimeout(() => { setSearch(query.trim()); setPage(1) }, 350)
    return () => clearTimeout(id)
  }, [query])

  useEffect(() => {
    const qs = new URLSearchParams({ page: String(page) })
    if (area) qs.set('action', area)
    if (search) qs.set('q', search)
    staffApi(`/api/admin/audit?${qs}`).then(setData)
  }, [area, page, search, staffApi])
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1

  return (
    <>
      <PageTitle title={t('admin.nav.audit')} />
      <p className="-mt-3 mb-4 text-sm text-muted">{t('audit.hint')}</p>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <label className="relative flex-1">
          <Search size={16} className="pointer-events-none absolute top-3 left-3 text-muted" />
          <input type="search" className={`${inputCls} pl-9`} placeholder={t('audit.search')} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={t('audit.search')} />
        </label>
        <select className={`${inputBase} w-full sm:w-56`} value={area} onChange={(e) => { setArea(e.target.value); setPage(1) }} aria-label={t('audit.area')}>
          {AREAS.map((a) => <option key={a} value={a}>{t(`audit.area.${a.replace('.', '') || 'all'}`)}</option>)}
        </select>
      </div>

      {!data ? <Skeleton className="h-60" /> : data.entries.length === 0 ? (
        <Card><p className="py-10 text-center text-muted">{t('audit.none')}</p></Card>
      ) : (
        <>
          {/* Phones */}
          <ul className="space-y-2.5 md:hidden">
            {data.entries.map((e) => <AuditCard key={e.id} e={e} />)}
          </ul>
          {/* Tablets and computers */}
          <Card className="hidden md:block">
            <table className="w-full table-fixed text-left text-sm">
              <thead className="border-b border-line text-xs uppercase tracking-wider text-muted">
                <tr>
                  <th className="w-44 py-2 pr-3 font-medium">{t('audit.when')}</th>
                  <th className="w-40 px-3 py-2 font-medium">{t('audit.who')}</th>
                  <th className="w-56 px-3 py-2 font-medium">{t('audit.what')}</th>
                  <th className="py-2 pl-3 font-medium">{t('audit.details')}</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e) => (
                  <tr key={e.id} className="border-b border-line align-top transition-colors last:border-0 hover:bg-surface-2/60">
                    <td className="py-2.5 pr-3 tabular-nums text-muted">{when(e.at).toLocaleString(appLocale(), { dateStyle: 'medium', timeStyle: 'short' })}</td>
                    <td className="px-3 py-2.5">{e.user || t('audit.system')}<span className="block text-xs text-muted">{e.ip}</span></td>
                    <td className="px-3 py-2.5 font-medium">{humanAction(e.action)}{e.entity_id && <span className="text-muted"> #{e.entity_id}</span>}</td>
                    <td className="py-2.5 pl-3"><Details details={e.details} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
      {data && pages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3 text-sm md:justify-end">
          <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('admin.prev')}</Button>
          <span className="tabular-nums text-muted">{page} / {pages}</span>
          <Button size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>{t('admin.next')}</Button>
        </div>
      )}
    </>
  )
}
