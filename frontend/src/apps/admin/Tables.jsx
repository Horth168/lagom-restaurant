/* Tables & QR codes: add, edit (name, seats, area), switch off, download/print QR, replace a QR. */
import { useCallback, useEffect, useState } from 'react'
import { Download, Minus, Pencil, Plus, Printer, RefreshCw } from 'lucide-react'
import { Sheet } from '../../components/Sheet'
import { Badge, Button, Card, Field, inputCls, Skeleton, useToast } from '../../components/ui'
import { useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const EMPTY = { label: '', seats: 4, area: '', is_active: true }

function IconAction({ label, onClick, children }) {
  return (
    <button onClick={onClick} title={label} aria-label={label}
      className="press grid size-10 place-items-center rounded-full text-ink transition-colors hover:bg-surface-2">
      {children}
    </button>
  )
}

export default function Tables() {
  const { t } = useI18n()
  const { staffApi, token } = useStaff()
  const toast = useToast()
  const [tables, setTables] = useState(null)
  const [edit, setEdit] = useState(null) // null | {…table} | {…EMPTY} for a new one
  const [busy, setBusy] = useState(false)

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

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    const body = { label: edit.label.trim(), seats: Math.max(1, Math.min(50, Number(edit.seats) || 1)), area: edit.area.trim() }
    try {
      if (edit.id) await staffApi(`/api/admin/tables/${edit.id}`, { method: 'PATCH', body: { ...body, is_active: edit.is_active } })
      else await staffApi('/api/admin/tables', { method: 'POST', body })
      toast(t('admin.saved'))
      setEdit(null)
      load()
    } catch (err) {
      toast(err.message, 'bad')
    } finally {
      setBusy(false)
    }
  }

  async function rotate(tbl) {
    if (!window.confirm(t('admin.tables.rotateConfirm', { table: tbl.label }))) return
    await staffApi(`/api/admin/tables/${tbl.id}/rotate-qr`, { method: 'POST' })
    toast(t('admin.tables.rotated'))
    load()
  }

  const seats = (n) => setEdit((x) => ({ ...x, seats: Math.max(1, Math.min(50, (Number(x.seats) || 1) + n)) }))

  return (
    <>
      <PageTitle title={t('admin.nav.tables')}>
        <Button onClick={() => openFile('/api/admin/tables/cards.pdf')}><Printer size={16} /> <span className="hidden sm:inline">{t('admin.tables.printAll')}</span><span className="sm:hidden">{t('admin.tables.printAllShort')}</span></Button>
        <Button variant="primary" onClick={() => setEdit({ ...EMPTY })}><Plus size={16} /> {t('admin.tables.add')}</Button>
      </PageTitle>
      <p className="-mt-3 mb-4 max-w-2xl text-sm text-muted">{t('admin.tables.hint')}</p>

      <Card>
        {!tables ? <Skeleton className="h-64" /> : tables.length === 0 ? (
          <p className="py-10 text-center text-muted">{t('admin.tables.none')}</p>
        ) : (
          <ul className="-my-2 divide-y divide-line">
            {tables.map((tbl) => (
              <li key={tbl.id} className={`flex flex-wrap items-center gap-x-3 gap-y-2 py-3 ${tbl.is_active ? '' : 'opacity-60'}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{tbl.label}</span>
                    {!tbl.is_active && <Badge tone="bad">{t('admin.tables.inactive')}</Badge>}
                    {tbl.active_orders > 0 && <Badge tone="info">{t('admin.openNow', { n: tbl.active_orders })}</Badge>}
                    {tbl.recent_sessions > 0 && <Badge>{t('admin.tables.phones', { n: tbl.recent_sessions })}</Badge>}
                  </div>
                  <div className="mt-0.5 text-sm text-muted">{t('admin.tables.seats', { n: tbl.seats })}{tbl.area && ` · ${tbl.area}`}</div>
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <IconAction label={t('admin.tables.edit')} onClick={() => setEdit({ ...tbl })}><Pencil size={17} /></IconAction>
                  <IconAction label={t('admin.tables.downloadQr')} onClick={() => openFile(`/api/admin/tables/${tbl.id}/qr.png?download=true`, `lagom-${tbl.label.replace(/\s+/g, '-').toLowerCase()}-qr.png`)}><Download size={17} /></IconAction>
                  <IconAction label={t('admin.tables.printCard')} onClick={() => openFile(`/api/admin/tables/cards.pdf?ids=${tbl.id}`)}><Printer size={17} /></IconAction>
                  <IconAction label={t('admin.tables.rotate')} onClick={() => rotate(tbl)}><RefreshCw size={17} /></IconAction>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Sheet open={!!edit} onClose={() => setEdit(null)} label={edit?.id ? t('admin.tables.edit') : t('admin.tables.add')}>
        {edit && (
          <form onSubmit={save} className="space-y-4 p-6">
            <h2 className="pr-10 font-display text-2xl">{edit.id ? t('admin.tables.editTitle', { table: edit.label }) : t('admin.tables.add')}</h2>
            <Field label={t('admin.tables.name')}>
              <input required maxLength={40} className={inputCls} value={edit.label} onChange={(e) => setEdit({ ...edit, label: e.target.value })} placeholder={t('admin.tables.nameExample')} />
            </Field>
            <div>
              <span className="text-sm font-medium">{t('admin.tables.seatsLabel')}</span>
              <div className="mt-1.5 flex items-center gap-3">
                <button type="button" onClick={() => seats(-1)} aria-label={t('product.decrease')} className="press grid size-11 place-items-center rounded-full border border-line"><Minus size={18} /></button>
                <input type="number" inputMode="numeric" min="1" max="50" aria-label={t('admin.tables.seatsLabel')}
                  className="h-11 w-16 rounded-lg border border-line bg-bg text-center text-lg font-semibold tabular-nums outline-none focus:border-accent"
                  value={edit.seats} onChange={(e) => setEdit({ ...edit, seats: e.target.value })} />
                <button type="button" onClick={() => seats(1)} aria-label={t('product.increase')} className="press grid size-11 place-items-center rounded-full border border-line"><Plus size={18} /></button>
              </div>
            </div>
            <Field label={t('admin.tables.area')}>
              <input maxLength={60} className={inputCls} value={edit.area} onChange={(e) => setEdit({ ...edit, area: e.target.value })} placeholder={t('admin.tables.areaExample')} />
            </Field>
            {edit.id && (
              <label className="flex items-start gap-3 rounded-xl bg-surface-2 p-3 text-sm">
                <input type="checkbox" className="mt-0.5" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
                <span><b>{t('admin.tables.inUse')}</b><span className="block text-muted">{t('admin.tables.inUseHint')}</span></span>
              </label>
            )}
            <Button variant="primary" size="lg" className="w-full" disabled={busy || !edit.label.trim()}>{t('admin.save')}</Button>
          </form>
        )}
      </Sheet>
    </>
  )
}
