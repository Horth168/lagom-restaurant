import { useCallback, useEffect, useState } from 'react'
import { KeyRound, Pencil, Plus, ShieldCheck } from 'lucide-react'
import { Sheet } from '../../components/Sheet'
import { Badge, Button, Card, Field, inputCls, Skeleton, useToast } from '../../components/ui'
import { LANGUAGES, appLocale, useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const ROLES = ['OWNER', 'ADMIN', 'CASHIER', 'KITCHEN', 'DRINKS', 'INVENTORY']

export default function StaffPage() {
  const { t } = useI18n()
  const { staffApi, user } = useStaff()
  const [rows, setRows] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [editing, setEditing] = useState(null)
  const [resetting, setResetting] = useState(null)
  const [showMatrix, setShowMatrix] = useState(false)

  const load = useCallback(async () => {
    const [list, roles] = await Promise.all([staffApi('/api/staff'), staffApi('/api/staff/roles')])
    setRows(list)
    setMatrix(roles)
  }, [staffApi])
  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <PageTitle title={t('admin.nav.staff')}>
        <Button onClick={() => setShowMatrix(true)}><ShieldCheck size={16} /> {t('staff.whoCanDoWhat')}</Button>
        <Button variant="primary" onClick={() => setEditing({})}><Plus size={16} /> {t('staff.add')}</Button>
      </PageTitle>
      <Card>
        {!rows ? <Skeleton className="h-60" /> : (
          <ul className="-my-2 divide-y divide-line">
            {rows.map((s) => (
              <li key={s.id} className={`flex items-center gap-3 py-3 ${s.is_active ? '' : 'opacity-55'}`}>
                <span className="grid size-11 shrink-0 place-items-center rounded-full bg-surface-2 font-semibold">{s.full_name.slice(0, 1).toUpperCase()}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-medium">{s.full_name}</span>
                    {s.id === user?.id && <span className="text-xs text-muted">({t('staff.you')})</span>}
                    <Badge tone={s.role === 'OWNER' ? 'info' : 'neutral'}>{t(`role.${s.role}`)}</Badge>
                    {s.extra_permissions.length > 0 && <Badge tone="warn">+{s.extra_permissions.length}</Badge>}
                    {!s.is_active && <Badge tone="bad">{t('staff.inactive')}</Badge>}
                  </span>
                  <span className="block truncate text-sm text-muted">{s.email}</span>
                  <span className="block text-xs text-muted">
                    {s.last_login_at ? t('staff.lastSeen', { date: new Date(s.last_login_at).toLocaleDateString(appLocale(), { day: 'numeric', month: 'short', year: 'numeric' }) }) : t('staff.neverSignedIn')}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-0.5">
                  <button onClick={() => setEditing(s)} aria-label={t('inv.edit')} title={t('inv.edit')} className="press grid size-10 place-items-center rounded-full hover:bg-surface-2"><Pencil size={17} /></button>
                  <button onClick={() => setResetting(s)} aria-label={t('staff.resetPassword')} title={t('staff.resetPassword')} className="press grid size-10 place-items-center rounded-full hover:bg-surface-2"><KeyRound size={17} /></button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {editing && matrix && <StaffSheet member={editing} matrix={matrix} onClose={() => setEditing(null)} onDone={() => { setEditing(null); load() }} />}
      {resetting && <ResetSheet member={resetting} onClose={() => setResetting(null)} />}
      {showMatrix && matrix && <MatrixSheet matrix={matrix} onClose={() => setShowMatrix(false)} />}
    </>
  )
}

function StaffSheet({ member, matrix, onClose, onDone }) {
  const { t } = useI18n()
  const { staffApi, user } = useStaff()
  const toast = useToast()
  const isNew = !member.id
  const [f, setF] = useState({ full_name: '', email: '', role: 'CASHIER', password: '', preferred_language: 'en', extra_permissions: [], is_active: true, ...member })
  const rolePerms = new Set(matrix.roles[f.role] || [])
  const extras = Object.keys(matrix.permissions).filter((p) => !rolePerms.has(p))
  const isSelf = member.id === user?.id

  async function save() {
    try {
      if (isNew) {
        await staffApi('/api/staff', { method: 'POST', body: { full_name: f.full_name, email: f.email, role: f.role, password: f.password,
          preferred_language: f.preferred_language, extra_permissions: f.extra_permissions } })
      } else {
        const body = { full_name: f.full_name, preferred_language: f.preferred_language, extra_permissions: f.extra_permissions }
        if (!isSelf) Object.assign(body, { role: f.role, is_active: f.is_active })
        await staffApi(`/api/staff/${member.id}`, { method: 'PATCH', body })
      }
      toast(t('admin.saved'))
      onDone()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  const toggleExtra = (p) => setF({ ...f, extra_permissions: f.extra_permissions.includes(p) ? f.extra_permissions.filter((x) => x !== p) : [...f.extra_permissions, p] })

  return (
    <Sheet open onClose={onClose} label={t('staff.add')}>
      <div className="space-y-4 p-6">
        <h2 className="font-display text-2xl">{isNew ? t('staff.add') : member.full_name}</h2>
        <Field label={t('staff.name')}><input className={inputCls} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        <Field label={t('login.email')}><input type="email" className={inputCls} value={f.email} disabled={!isNew} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        {isNew && (
          <Field label={t('staff.firstPassword')} hint={t('staff.passwordRules')}>
            <input type="text" autoComplete="new-password" className={inputCls} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('staff.role')} hint={isSelf ? t('staff.ownRole') : undefined}>
            <select className={inputCls} value={f.role} disabled={isSelf} onChange={(e) => setF({ ...f, role: e.target.value, extra_permissions: [] })}>
              {ROLES.map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}
            </select>
          </Field>
          <Field label={t('lang.title')}>
            <select className={inputCls} value={f.preferred_language} onChange={(e) => setF({ ...f, preferred_language: e.target.value })}>
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </Field>
        </div>
        <div className="rounded-lg bg-surface-2 p-3 text-sm">
          <div className="font-medium">{t('staff.roleCan')}</div>
          <p className="mt-1 text-muted">{[...rolePerms].map((p) => t(`perm.${p}`)).join(' · ')}</p>
        </div>
        {extras.length > 0 && (
          <div>
            <div className="text-sm font-medium">{t('staff.extra')}</div>
            <p className="text-xs text-muted">{t('staff.extraHint')}</p>
            <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
              {extras.map((p) => (
                <label key={p} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.extra_permissions.includes(p)} onChange={() => toggleExtra(p)} /> {t(`perm.${p}`)}</label>
              ))}
            </div>
          </div>
        )}
        {!isNew && !isSelf && (
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('staff.activeHint')}</label>
        )}
        <Button variant="primary" size="lg" className="w-full" disabled={!f.full_name.trim() || (isNew && (!f.email || f.password.length < 10))} onClick={save}>{t('admin.save')}</Button>
        {!isNew && <p className="text-xs text-muted">{t('staff.signOutNote')}</p>}
      </div>
    </Sheet>
  )
}

function ResetSheet({ member, onClose }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [pw, setPw] = useState('')
  async function save() {
    try {
      await staffApi(`/api/staff/${member.id}/reset-password`, { method: 'POST', body: { new_password: pw } })
      toast(t('staff.passwordReset'))
      onClose()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  return (
    <Sheet open onClose={onClose} label={t('staff.resetPassword')}>
      <div className="space-y-4 p-6">
        <h2 className="font-display text-2xl">{t('staff.resetPassword')}</h2>
        <p className="text-sm text-muted">{member.full_name} · {member.email}</p>
        <Field label={t('acct.newPassword')} hint={t('staff.passwordRules')}><input type="text" autoComplete="new-password" className={inputCls} value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        <p className="text-xs text-muted">{t('staff.resetNote')}</p>
        <Button variant="primary" size="lg" className="w-full" disabled={pw.length < 10} onClick={save}>{t('staff.resetPassword')}</Button>
      </div>
    </Sheet>
  )
}

function MatrixSheet({ matrix, onClose }) {
  const { t } = useI18n()
  return (
    <Sheet open onClose={onClose} label={t('staff.whoCanDoWhat')}>
      <div className="p-6">
        <h2 className="font-display text-2xl">{t('staff.whoCanDoWhat')}</h2>
        <div className="mt-4 space-y-3 sm:hidden">
          {ROLES.map((r) => (
            <details key={r} className="group rounded-xl bg-surface-2/70 p-3">
              <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
                {t(`role.${r}`)} <span className="text-xs text-muted">{(matrix.roles[r] || []).length}</span>
              </summary>
              <ul className="mt-2 space-y-1 text-sm">
                {Object.keys(matrix.permissions).filter((p) => matrix.roles[r]?.includes(p)).map((p) => (
                  <li key={p} className="flex gap-2"><span className="text-series-1">●</span>{t(`perm.${p}`)}</li>
                ))}
              </ul>
            </details>
          ))}
        </div>
        <div className="mt-4 hidden overflow-x-auto sm:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-muted">
                <th className="py-2 text-left font-medium" />
                {ROLES.map((r) => <th key={r} className="px-1 py-2 font-medium">{t(`role.${r}`)}</th>)}
              </tr>
            </thead>
            <tbody>
              {Object.keys(matrix.permissions).map((p) => (
                <tr key={p} className="border-t border-line">
                  <td className="py-1.5 pr-2">{t(`perm.${p}`)}</td>
                  {ROLES.map((r) => (
                    <td key={r} className="text-center" aria-label={matrix.roles[r]?.includes(p) ? t('staff.yes') : t('staff.no')}>
                      {matrix.roles[r]?.includes(p) ? <span className="text-series-1">●</span> : <span className="text-line">○</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-muted">{t('staff.matrixNote')}</p>
      </div>
    </Sheet>
  )
}
