import { useCallback, useEffect, useState } from 'react'
import { Download, Plus, Printer, RefreshCw } from 'lucide-react'
import { Badge, Button, Card, Field, inputCls, Skeleton, useToast } from '../../components/ui'
import { useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

export default function Tables() {
  const { t } = useI18n()
  const { staffApi, token } = useStaff()
  const toast = useToast()
  const [tables, setTables] = useState(null)
  const [form, setForm] = useState({ label: '', seats: 4, area: '' })

  const load = useCallback(async () => setTables(await staffApi('/api/admin/tables')), [staffApi])
  useEffect(() => {
    load()
  }, [load])

  // Files need the login token, so they are fetched and then opened/saved locally
  async function openFile(path, filename) {
    const res = await fetch(`${import.meta.env.VITE_API_URL || ''}${path}`, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) return toast(t('admin.failed'), 'bad')
    const url = URL.createObjectURL(await res.blob())
    if (filename) {
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
    } else {
      window.open(url, '_blank', 'noopener')
    }
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  }

  async function add(e) {
    e.preventDefault()
    try {
      await staffApi('/api/admin/tables', { method: 'POST', body: { ...form, seats: Number(form.seats) || 1 } })
      setForm({ label: '', seats: 4, area: '' })
      toast(t('admin.saved'))
      load()
    } catch (err) {
      toast(err.message, 'bad')
    }
  }

  async function update(tbl, body, msg) {
    try {
      await staffApi(`/api/admin/tables/${tbl.id}`, { method: 'PATCH', body })
      toast(msg)
      load()
    } catch (err) {
      toast(err.message, 'bad')
    }
  }

  async function rotate(tbl) {
    if (!window.confirm(t('admin.tables.rotateConfirm', { table: tbl.label }))) return
    await staffApi(`/api/admin/tables/${tbl.id}/rotate-qr`, { method: 'POST' })
    toast(t('admin.tables.rotated'))
    load()
  }

  return (
    <>
      <PageTitle title={t('admin.nav.tables')}>
        <Button onClick={() => openFile('/api/admin/tables/cards.pdf')}><Printer size={16} /> {t('admin.tables.printAll')}</Button>
      </PageTitle>
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <Card>
          {!tables ? <Skeleton className="h-64" /> : (
            <ul className="-my-2 divide-y divide-line">
              {tables.map((tbl) => (
                <li key={tbl.id} className="flex flex-wrap items-center gap-3 py-3">
                  <span className="min-w-28 font-semibold">{tbl.label}</span>
                  <span className="text-sm text-muted">{t('admin.tables.seats', { n: tbl.seats })}{tbl.area && ` · ${tbl.area}`}</span>
                  {tbl.active_orders > 0 && <Badge tone="info">{t('admin.openNow', { n: tbl.active_orders })}</Badge>}
                  {tbl.recent_sessions > 0 && <Badge>{t('admin.tables.phones', { n: tbl.recent_sessions })}</Badge>}
                  {!tbl.is_active && <Badge tone="bad">{t('admin.tables.inactive')}</Badge>}
                  <span className="ml-auto flex flex-wrap gap-1">
                    <Button size="sm" variant="ghost" onClick={() => openFile(`/api/admin/tables/${tbl.id}/qr.png?download=true`, `lagom-${tbl.label.replace(/\s+/g, '-').toLowerCase()}-qr.png`)} title={t('admin.tables.downloadQr')}><Download size={15} /> QR</Button>
                    <Button size="sm" variant="ghost" onClick={() => openFile(`/api/admin/tables/cards.pdf?ids=${tbl.id}`)} title={t('admin.tables.printCard')}><Printer size={15} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => rotate(tbl)} title={t('admin.tables.rotate')}><RefreshCw size={15} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => update(tbl, { is_active: !tbl.is_active }, t('admin.saved'))}>
                      {tbl.is_active ? t('admin.tables.deactivate') : t('admin.tables.activate')}
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title={t('admin.tables.add')}>
          <form onSubmit={add} className="space-y-3">
            <Field label={t('admin.tables.name')}><input required className={inputCls} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Table 13" /></Field>
            <Field label={t('admin.tables.seatsLabel')}><input type="number" min="1" max="50" className={inputCls} value={form.seats} onChange={(e) => setForm({ ...form, seats: e.target.value })} /></Field>
            <Field label={t('admin.tables.area')}><input className={inputCls} value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })} placeholder="Terrace" /></Field>
            <Button variant="primary" className="w-full"><Plus size={16} /> {t('admin.tables.add')}</Button>
          </form>
          <p className="mt-4 text-xs text-muted">{t('admin.tables.hint')}</p>
        </Card>
      </div>
    </>
  )
}
