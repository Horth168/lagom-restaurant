import { useEffect, useState } from 'react'
import { Button, Card, inputBase, Skeleton } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const AREAS = ['', 'auth.', 'staff.', 'order.', 'payment.', 'menu.', 'inventory.', 'finance.', 'settings.', 'table.']

export default function AuditLog() {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const [area, setArea] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)

  useEffect(() => {
    const qs = new URLSearchParams({ page: String(page) })
    if (area) qs.set('action', area)
    staffApi(`/api/admin/audit?${qs}`).then(setData)
  }, [area, page, staffApi])
  const pages = data ? Math.max(1, Math.ceil(data.total / data.per_page)) : 1

  return (
    <>
      <PageTitle title={t('admin.nav.audit')}>
        <select className={`${inputBase} w-52`} value={area} onChange={(e) => { setArea(e.target.value); setPage(1) }} aria-label={t('audit.area')}>
          {AREAS.map((a) => <option key={a} value={a}>{t(`audit.area.${a.replace('.', '') || 'all'}`)}</option>)}
        </select>
      </PageTitle>
      <Card>
        <p className="mb-3 text-xs text-muted">{t('audit.hint')}</p>
        {!data ? <Skeleton className="h-60" /> : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-line text-xs uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-5 py-2 font-medium">{t('audit.when')}</th>
                  <th className="px-3 py-2 font-medium">{t('audit.who')}</th>
                  <th className="px-3 py-2 font-medium">{t('audit.what')}</th>
                  <th className="px-5 py-2 font-medium">{t('audit.details')}</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e) => (
                  <tr key={e.id} className="border-b border-line align-top last:border-0">
                    <td className="whitespace-nowrap px-5 py-2.5 tabular-nums text-muted">{new Date(e.at).toLocaleString(appLocale())}</td>
                    <td className="px-3 py-2.5">{e.user || '—'}<span className="block text-xs text-muted">{e.ip}</span></td>
                    <td className="px-3 py-2.5 font-mono text-xs">{e.action}{e.entity_id && <span className="text-muted"> #{e.entity_id}</span>}</td>
                    <td className="max-w-md px-5 py-2.5 text-xs text-muted break-words">
                      {Object.entries(e.details || {}).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && pages > 1 && (
          <div className="mt-4 flex items-center justify-end gap-2 text-sm">
            <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('admin.prev')}</Button>
            <span className="tabular-nums text-muted">{page} / {pages}</span>
            <Button size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>{t('admin.next')}</Button>
          </div>
        )}
      </Card>
    </>
  )
}
