import { useCallback, useEffect, useState } from 'react'
import { FileSpreadsheet, FileText, Pencil, Plus, Trash2 } from 'lucide-react'
import { Sheet } from '../../components/Sheet'
import { Button, Card, centsToInput, Field, inputBase, inputCls, parseUsd, Skeleton, useToast } from '../../components/ui'
import { useI18n } from '../../i18n'
import { formatKHR, formatUSD } from '../../lib/money'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const PERIODS = ['today', '7d', 'month', 'last_month', 'quarter', 'year', 'custom']
const GROUPS = ['', 'day', 'week', 'month', 'quarter', 'year']
const CATEGORIES = ['INGREDIENTS', 'SALARIES', 'RENT', 'ELECTRICITY', 'WATER', 'PACKAGING', 'MARKETING', 'EQUIPMENT', 'OTHER']

export default function Finance() {
  const { t } = useI18n()
  const { can } = useStaff()
  const [tab, setTab] = useState('report')
  const [period, setPeriod] = useState('month')
  const [range, setRange] = useState({ start: '', end: '' })
  const [group, setGroup] = useState('')
  const qs = period === 'custom' ? `period=custom&start=${range.start}&end=${range.end}` : `period=${period}`
  const ready = period !== 'custom' || (range.start && range.end)

  return (
    <>
      <PageTitle title={t('admin.nav.finance')}>
        <div className="flex gap-1 rounded-lg border border-line bg-surface p-1" role="tablist">
          {['report', 'expenses'].map((x) => (
            <button key={x} role="tab" aria-selected={tab === x} onClick={() => setTab(x)}
              className={`rounded-md px-3 py-1.5 text-sm ${tab === x ? 'bg-brand text-on-brand' : 'hover:bg-surface-2'}`}>{t(`fin.tab.${x}`)}</button>
          ))}
        </div>
      </PageTitle>
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1 rounded-lg border border-line bg-surface p-1">
          {PERIODS.map((p) => (
            <button key={p} onClick={() => setPeriod(p)} className={`rounded-md px-3 py-1.5 text-sm ${period === p ? 'bg-brand text-on-brand' : 'hover:bg-surface-2'}`}>
              {t(`admin.period.${p}`)}
            </button>
          ))}
        </div>
        {period === 'custom' && (
          <>
            <input type="date" className={`${inputBase} w-40`} value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} aria-label={t('admin.from')} />
            <input type="date" className={`${inputBase} w-40`} value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} aria-label={t('admin.to')} />
          </>
        )}
        {tab === 'report' && (
          <select className={`${inputBase} w-40`} value={group} onChange={(e) => setGroup(e.target.value)} aria-label={t('fin.groupBy')}>
            {GROUPS.map((g) => <option key={g} value={g}>{g ? t(`fin.group.${g}`) : t('fin.group.auto')}</option>)}
          </select>
        )}
      </div>
      {!ready ? null : tab === 'report' ? <Report qs={qs + (group ? `&group=${group}` : '')} /> : <Expenses qs={qs} editable={can('finance.edit')} />}
    </>
  )
}

function Report({ qs }) {
  const { t } = useI18n()
  const { staffApi, token } = useStaff()
  const toast = useToast()
  const [r, setR] = useState(null)
  useEffect(() => {
    setR(null)
    staffApi(`/api/admin/finance/report?${qs}`).then(setR).catch((e) => toast(e.message, 'bad'))
  }, [qs, staffApi, toast])

  async function download(ext) {
    const res = await fetch(`${import.meta.env.VITE_API_URL || ''}/api/admin/finance/report.${ext}?${qs}`, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) return toast(t('admin.failed'), 'bad')
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = (res.headers.get('content-disposition') || '').match(/filename="(.+)"/)?.[1] || `lagom-finance.${ext}`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  }

  if (!r) return <Skeleton className="h-96" />
  const lines = [
    ['fin.gross', r.gross_sales_usd_cents, 0], ['fin.discounts', -r.discounts_usd_cents, 0], ['fin.net', r.net_sales_usd_cents, 1],
    ['fin.refunds', -r.refunds_usd_cents, 0], ['fin.cogs', -r.cogs_usd_cents, 0], ['fin.waste', -r.waste_usd_cents, 0],
    ['fin.grossProfit', r.gross_profit_usd_cents, 1], ['fin.expenses', -r.expenses_usd_cents, 0], ['fin.netProfit', r.net_profit_usd_cents, 2],
  ]
  const maxCat = Math.max(...Object.values(r.expenses_by_category), 1)
  const money = (c) => (c < 0 ? `-${formatUSD(-c)}` : formatUSD(c))
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label={t('fin.net')} value={formatUSD(r.net_sales_usd_cents)} sub={t('admin.ordersCount', { n: r.orders })} />
        <Tile label={t('fin.grossProfit')} value={money(r.gross_profit_usd_cents)} sub={r.gross_margin_percent != null ? t('fin.margin', { n: r.gross_margin_percent }) : ''} />
        <Tile label={t('fin.expenses')} value={formatUSD(r.expenses_usd_cents)} />
        <Tile label={t('fin.netProfit')} value={money(r.net_profit_usd_cents)} hero negative={r.net_profit_usd_cents < 0} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <Card title={t('fin.statement')} action={
          <span className="flex gap-2">
            <Button size="sm" onClick={() => download('xlsx')}><FileSpreadsheet size={15} /> Excel</Button>
            <Button size="sm" onClick={() => download('pdf')}><FileText size={15} /> PDF</Button>
          </span>
        }>
          <dl className="divide-y divide-line text-sm">
            {lines.map(([k, v, strong]) => (
              <div key={k} className={`flex justify-between py-2.5 ${strong ? 'font-semibold' : ''} ${strong === 2 ? 'text-base' : ''}`}>
                <dt className={strong ? '' : 'pl-3 text-muted'}>{t(k)}</dt>
                <dd className={`tabular-nums ${v < 0 && strong ? 'text-danger' : ''}`}>{money(v)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-muted">{t('fin.note')}</p>
        </Card>
        <div className="space-y-6">
          <Card title={t('fin.byCategory')}>
            {r.expenses_usd_cents === 0 ? <p className="text-sm text-muted">{t('fin.noExpenses')}</p> : (
              <ul className="space-y-2.5 text-sm">
                {Object.entries(r.expenses_by_category).filter(([, v]) => v).sort((a, b) => b[1] - a[1]).map(([cat, v]) => (
                  <li key={cat}>
                    <div className="flex justify-between"><span>{t(`fin.cat.${cat}`)}</span><span className="tabular-nums">{formatUSD(v)}</span></div>
                    <div className="mt-1 h-1.5 rounded-full bg-surface-2"><div className="h-full rounded-full bg-series-1" style={{ width: `${(v / maxCat) * 100}%` }} /></div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title={t('fin.other')}>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-muted">{t('pay.khqr')}</dt><dd className="tabular-nums">{formatUSD(r.sales_by_method.khqr || 0)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">{t('pos.cash')}</dt><dd className="tabular-nums">{formatUSD(r.sales_by_method.cash || 0)}</dd></div>
              <div className="flex justify-between"><dt className="text-muted">{t('fin.purchases')}</dt><dd className="tabular-nums">{formatUSD(r.purchases_usd_cents)}</dd></div>
            </dl>
            <p className="mt-3 text-xs text-muted">{t('fin.purchasesNote')}</p>
          </Card>
        </div>
      </div>
      <Card title={t(`fin.group.${r.period.group}`)}>
        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-[720px] text-right text-sm tabular-nums">
            <thead className="border-b border-line text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-5 py-2 text-left font-medium">{t('fin.period')}</th>
                {['admin.stat.orders', 'fin.net', 'fin.refunds', 'fin.cogs', 'fin.waste', 'fin.grossProfit', 'fin.expenses', 'fin.netProfit'].map((k) => <th key={k} className="px-3 py-2 font-medium">{t(k)}</th>)}
              </tr>
            </thead>
            <tbody>
              {r.periods.length === 0 && <tr><td colSpan={9} className="px-5 py-8 text-center text-muted">{t('admin.noSales')}</td></tr>}
              {r.periods.map((p) => (
                <tr key={p.label} className="border-b border-line last:border-0">
                  <td className="px-5 py-2.5 text-left">{p.label}</td>
                  <td className="px-3 py-2.5">{p.orders}</td>
                  <td className="px-3 py-2.5">{formatUSD(p.net_sales)}</td>
                  <td className="px-3 py-2.5">{formatUSD(p.refunds)}</td>
                  <td className="px-3 py-2.5">{formatUSD(p.cogs)}</td>
                  <td className="px-3 py-2.5">{formatUSD(p.waste)}</td>
                  <td className="px-3 py-2.5">{money(p.gross_profit)}</td>
                  <td className="px-3 py-2.5">{formatUSD(p.expenses)}</td>
                  <td className={`px-3 py-2.5 font-semibold ${p.net_profit < 0 ? 'text-danger' : ''}`}>{money(p.net_profit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function Tile({ label, value, sub, hero, negative }) {
  return (
    <div className={`rounded-xl border border-line p-5 ${hero ? 'bg-forest text-cream' : 'bg-surface'}`}>
      <div className={`text-sm ${hero ? 'text-cream/75' : 'text-muted'}`}>{label}</div>
      <div className={`mt-2 font-display text-3xl tabular-nums ${negative ? 'text-[#ffb3a6]' : ''}`}>{value}</div>
      {sub && <div className={`mt-1 text-xs ${hero ? 'text-cream/70' : 'text-muted'}`}>{sub}</div>}
    </div>
  )
}

function Expenses({ qs, editable }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [rows, setRows] = useState(null)
  const [editing, setEditing] = useState(null)
  const load = useCallback(() => staffApi(`/api/admin/finance/expenses?${qs}`).then(setRows), [qs, staffApi])
  useEffect(() => {
    load()
  }, [load])
  async function remove(x) {
    if (!window.confirm(t('fin.deleteConfirm', { what: x.description }))) return
    await staffApi(`/api/admin/finance/expenses/${x.id}`, { method: 'DELETE' })
    toast(t('fin.deleted'))
    load()
  }
  const total = (rows ?? []).reduce((s, x) => s + x.amount_usd_cents, 0)
  return (
    <>
      <Card title={t('fin.tab.expenses')} action={editable && <Button size="sm" variant="primary" onClick={() => setEditing({})}><Plus size={14} /> {t('fin.addExpense')}</Button>}>
        {!rows ? <Skeleton className="h-40" /> : rows.length === 0 ? <p className="text-sm text-muted">{t('fin.noExpenses')}</p> : (
          <ul className="-my-2 divide-y divide-line text-sm">
            {rows.map((x) => (
              <li key={x.id} className="flex items-center gap-3 py-3">
                <span className="w-24 tabular-nums text-muted">{x.spent_on}</span>
                <span className="flex-1"><span className="font-medium">{x.description}</span><span className="block text-xs text-muted">{t(`fin.cat.${x.category}`)}{x.created_by && ` · ${x.created_by}`}</span></span>
                <span className="text-right tabular-nums">
                  <span className="font-semibold">{x.currency === 'KHR' ? formatKHR(x.amount_minor) : formatUSD(x.amount_minor)}</span>
                  {x.currency === 'KHR' && <span className="block text-xs text-muted">{formatUSD(x.amount_usd_cents)} @ {Number(x.khr_per_usd).toLocaleString()}</span>}
                </span>
                {editable && (
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(x)} aria-label={t('inv.edit')}><Pencil size={15} /></Button>
                    <Button size="sm" variant="ghost" onClick={() => remove(x)} aria-label={t('admin.remove')}><Trash2 size={15} /></Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {rows?.length > 0 && <div className="mt-4 flex justify-between border-t border-line pt-3 font-semibold"><span>{t('cart.total')}</span><span className="tabular-nums">{formatUSD(total)}</span></div>}
      </Card>
      {editing && <ExpenseSheet expense={editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); load() }} />}
    </>
  )
}

function ExpenseSheet({ expense, onClose, onDone }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const isNew = !expense.id
  const [f, setF] = useState(() => ({
    category: expense.category || 'OTHER', spent_on: expense.spent_on || new Date().toLocaleDateString('en-CA'),
    description: expense.description || '', currency: expense.currency || 'USD', notes: expense.notes || '',
    amount: expense.amount_minor == null ? '' : expense.currency === 'KHR' ? String(expense.amount_minor) : centsToInput(expense.amount_minor),
  }))
  const amountMinor = f.currency === 'KHR' ? (/^\d+$/.test(f.amount.replace(/,/g, '')) ? Number(f.amount.replace(/,/g, '')) : null) : parseUsd(f.amount)
  async function save() {
    const body = { category: f.category, spent_on: f.spent_on, description: f.description, currency: f.currency, amount_minor: amountMinor, notes: f.notes }
    try {
      if (isNew) await staffApi('/api/admin/finance/expenses', { method: 'POST', body })
      else await staffApi(`/api/admin/finance/expenses/${expense.id}`, { method: 'PUT', body })
      toast(t('admin.saved'))
      onDone()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  const bind = (k) => ({ value: f[k], onChange: (e) => setF({ ...f, [k]: e.target.value }) })
  return (
    <Sheet open onClose={onClose} label={t('fin.addExpense')}>
      <div className="space-y-4 p-6">
        <h2 className="font-display text-2xl">{isNew ? t('fin.addExpense') : expense.description}</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('inv.date')}><input type="date" className={inputCls} {...bind('spent_on')} /></Field>
          <Field label={t('fin.category')}>
            <select className={inputCls} {...bind('category')}>{CATEGORIES.map((c) => <option key={c} value={c}>{t(`fin.cat.${c}`)}</option>)}</select>
          </Field>
        </div>
        <Field label={t('fin.description')}><input className={inputCls} {...bind('description')} placeholder={t('fin.descriptionHint')} /></Field>
        <div className="grid grid-cols-[110px_1fr] gap-3">
          <Field label={t('fin.currency')}>
            <select className={inputCls} {...bind('currency')} disabled={!isNew}><option value="USD">USD $</option><option value="KHR">KHR ៛</option></select>
          </Field>
          <Field label={t('fin.amount')}><input className={inputCls} inputMode="decimal" {...bind('amount')} placeholder={f.currency === 'KHR' ? '400000' : '100.00'} /></Field>
        </div>
        {f.currency === 'KHR' && <p className="text-xs text-muted">{t('fin.rateNote')}</p>}
        <Field label={t('fin.notes')}><input className={inputCls} {...bind('notes')} /></Field>
        <Button variant="primary" size="lg" className="w-full" disabled={!f.description.trim() || !amountMinor} onClick={save}>{t('admin.save')}</Button>
      </div>
    </Sheet>
  )
}
