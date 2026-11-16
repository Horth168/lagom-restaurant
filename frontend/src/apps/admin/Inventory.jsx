import { Segmented } from '../../components/Segmented'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, History, Pencil, Plus, Trash2 } from 'lucide-react'
import { Sheet } from '../../components/Sheet'
import { Badge, Button, Card, Field, inputCls, parseUsd, Skeleton, useToast } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { formatUSD } from '../../lib/money'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const TABS = ['stock', 'purchases', 'suppliers', 'recipes']
const num = (s) => Number(s).toLocaleString('en-US', { maximumFractionDigits: 3 })
// Cost per unit is stored in thousandths of a cent so 1 g of coffee can cost $0.025 exactly
const unitCost = (millicents) => `$${(millicents / 100000).toFixed(4).replace(/0{1,2}$/, '')}`

export default function Inventory() {
  const { t } = useI18n()
  const { staffApi, can } = useStaff()
  const [tab, setTab] = useState('stock')
  const [ingredients, setIngredients] = useState(null)
  const [suppliers, setSuppliers] = useState([])
  const editable = can('inventory.edit')

  const load = useCallback(async () => {
    const [i, s] = await Promise.all([staffApi('/api/admin/inventory/ingredients'), staffApi('/api/admin/inventory/suppliers')])
    setIngredients(i)
    setSuppliers(s)
  }, [staffApi])
  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <PageTitle title={t('admin.nav.inventory')}>
        <Segmented label={t('admin.nav.inventory')} value={tab} onChange={setTab}
          options={TABS.map((x) => ({ value: x, label: t(`inv.tab.${x}`) }))} />
      </PageTitle>
      {!ingredients ? <Skeleton className="h-80" /> : (
        <>
          {tab === 'stock' && <Stock ingredients={ingredients} suppliers={suppliers} editable={editable} reload={load} />}
          {tab === 'purchases' && <Purchases ingredients={ingredients} suppliers={suppliers} editable={editable} reload={load} />}
          {tab === 'suppliers' && <Suppliers suppliers={suppliers} editable={editable} reload={load} />}
          {tab === 'recipes' && <Recipes ingredients={ingredients} editable={editable} />}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------- stock
function Stock({ ingredients, suppliers, editable, reload }) {
  const { t } = useI18n()
  const [adjusting, setAdjusting] = useState(null)
  const [history, setHistory] = useState(null)
  const [editing, setEditing] = useState(null)
  const value = ingredients.reduce((s, i) => s + i.stock_value_usd_cents, 0)
  const low = ingredients.filter((i) => i.is_low && i.is_active)
  return (
    <>
      <div className="mb-5 grid grid-cols-3 gap-2 sm:mb-6 sm:gap-4">
        <Tile label={t('inv.stockValue')} value={formatUSD(value)} />
        <Tile label={t('inv.ingredients')} value={ingredients.filter((i) => i.is_active).length} />
        <Tile label={t('admin.lowStock')} value={low.length} warn={low.length > 0} />
      </div>
      <Card title={t('inv.tab.stock')} action={editable && <Button size="sm" variant="primary" onClick={() => setEditing({})}><Plus size={14} /> {t('inv.addIngredient')}</Button>}>
        {/* Phones: one card per ingredient */}
        <ul className="-mx-1 divide-y divide-line md:hidden">
          {ingredients.length === 0 && <li className="py-8 text-center text-sm text-muted">{t('inv.none')}</li>}
          {ingredients.map((i) => (
            <li key={i.id} className={`px-1 py-3 ${i.is_active ? '' : 'opacity-50'}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium">{i.name}</div>
                  <div className="mt-0.5 text-xs text-muted">{unitCost(i.unit_cost_usd_millicents)} / {i.unit}{i.supplier ? ` · ${i.supplier}` : ''}</div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="font-semibold tabular-nums">{num(i.quantity)} {i.unit}</div>
                  {i.is_low
                    ? <div className="inline-flex items-center gap-1 text-xs font-semibold text-series-2"><AlertTriangle size={12} /> {t('inv.low')}</div>
                    : <div className="text-xs tabular-nums text-muted">{formatUSD(i.stock_value_usd_cents)}</div>}
                </div>
              </div>
              <div className="mt-2 flex gap-1.5">
                {editable && <Button size="sm" onClick={() => setAdjusting(i)}>{t('inv.adjust')}</Button>}
                <Button size="sm" variant="ghost" onClick={() => setHistory(i)} aria-label={t('inv.history')}><History size={15} /></Button>
                {editable && <Button size="sm" variant="ghost" onClick={() => setEditing(i)} aria-label={t('inv.edit')}><Pencil size={15} /></Button>}
              </div>
            </li>
          ))}
        </ul>
        <div className="-mx-5 hidden overflow-x-auto md:block">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-5 py-2 font-medium">{t('inv.ingredient')}</th>
                <th className="px-3 py-2 text-right font-medium">{t('inv.onHand')}</th>
                <th className="px-3 py-2 text-right font-medium">{t('inv.alertAt')}</th>
                <th className="px-3 py-2 text-right font-medium">{t('inv.costPerUnit')}</th>
                <th className="px-3 py-2 text-right font-medium">{t('inv.value')}</th>
                <th className="px-3 py-2 font-medium">{t('inv.supplier')}</th>
                <th className="px-5 py-2" />
              </tr>
            </thead>
            <tbody>
              {ingredients.map((i) => (
                <tr key={i.id} className={`border-b border-line last:border-0 ${i.is_active ? '' : 'opacity-50'}`}>
                  <td className="px-5 py-3 font-medium">
                    {i.name} {i.is_low && <span className="ml-1 inline-flex items-center gap-1 text-xs font-semibold text-series-2"><AlertTriangle size={13} /> {t('inv.low')}</span>}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">{num(i.quantity)} {i.unit}</td>
                  <td className="px-3 py-3 text-right tabular-nums text-muted">{num(i.low_stock_threshold)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{unitCost(i.unit_cost_usd_millicents)} / {i.unit}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{formatUSD(i.stock_value_usd_cents)}</td>
                  <td className="px-3 py-3 text-muted">{i.supplier || '—'}</td>
                  <td className="px-5 py-3">
                    <span className="flex justify-end gap-1">
                      {editable && <Button size="sm" onClick={() => setAdjusting(i)}>{t('inv.adjust')}</Button>}
                      <Button size="sm" variant="ghost" onClick={() => setHistory(i)} title={t('inv.history')}><History size={15} /></Button>
                      {editable && <Button size="sm" variant="ghost" onClick={() => setEditing(i)} title={t('inv.edit')}><Pencil size={15} /></Button>}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {adjusting && <AdjustSheet ingredient={adjusting} onClose={() => setAdjusting(null)} onDone={() => { setAdjusting(null); reload() }} />}
      {history && <HistorySheet ingredient={history} onClose={() => setHistory(null)} />}
      {editing && <IngredientSheet ingredient={editing} suppliers={suppliers} onClose={() => setEditing(null)} onDone={() => { setEditing(null); reload() }} />}
    </>
  )
}

function Tile({ label, value, warn }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface p-3 sm:p-5">
      <div className="flex items-center gap-1 truncate text-xs text-muted sm:text-sm">{warn && <AlertTriangle size={13} className="shrink-0 text-series-2" />}<span className="truncate">{label}</span></div>
      <div className="mt-1 font-display text-xl tabular-nums sm:mt-2 sm:text-3xl">{value}</div>
    </div>
  )
}

function AdjustSheet({ ingredient: i, onClose, onDone }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [mode, setMode] = useState('count')
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  async function save() {
    const body = { ingredient_id: i.id, note, kind: mode === 'waste' ? 'WASTE' : 'ADJUSTMENT' }
    if (mode === 'count') body.counted_quantity = amount
    else body.change = mode === 'remove' ? `-${amount}` : amount
    try {
      await staffApi('/api/admin/inventory/adjustments', { method: 'POST', body })
      toast(t('admin.saved'))
      onDone()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  return (
    <Sheet open onClose={onClose} label={t('inv.adjust')}>
      <div className="space-y-4 p-6">
        <h2 className="font-display text-2xl">{i.name}</h2>
        <p className="text-sm text-muted">{t('inv.onHand')}: <b className="text-ink">{num(i.quantity)} {i.unit}</b></p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {['count', 'add', 'remove', 'waste'].map((m) => (
            <button key={m} onClick={() => setMode(m)} className={`h-10 rounded-lg border text-sm ${mode === m ? 'border-brand bg-brand text-on-brand' : 'border-line'}`}>{t(`inv.mode.${m}`)}</button>
          ))}
        </div>
        <Field label={mode === 'count' ? t('inv.countedQty', { unit: i.unit }) : t('inv.amount', { unit: i.unit })}>
          <input className={inputCls} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
        </Field>
        <Field label={t('inv.reason')}><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t(`inv.reasonHint.${mode}`)} /></Field>
        <Button variant="primary" size="lg" className="w-full" disabled={!amount || isNaN(Number(amount)) || !note.trim()} onClick={save}>{t('admin.save')}</Button>
      </div>
    </Sheet>
  )
}

function HistorySheet({ ingredient: i, onClose }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const [rows, setRows] = useState(null)
  useEffect(() => {
    staffApi(`/api/admin/inventory/ingredients/${i.id}/movements`).then(setRows)
  }, [i.id, staffApi])
  return (
    <Sheet open onClose={onClose} label={t('inv.history')}>
      <div className="p-6">
        <h2 className="font-display text-2xl">{i.name}</h2>
        {!rows ? <Skeleton className="mt-4 h-40" /> : rows.length === 0 ? <p className="mt-4 text-sm text-muted">{t('inv.noMoves')}</p> : (
          <ul className="mt-4 divide-y divide-line text-sm">
            {rows.map((m) => (
              <li key={m.id} className="flex items-center gap-3 py-2.5">
                <Badge tone={Number(m.change) < 0 ? 'warn' : 'good'}>{t(`inv.kind.${m.kind}`)}</Badge>
                <span className="flex-1 truncate text-muted">{m.note}<span className="block text-xs">{new Date(m.created_at).toLocaleString(appLocale())}</span></span>
                <span className={`tabular-nums font-semibold ${Number(m.change) < 0 ? 'text-danger' : 'text-series-1'}`}>{Number(m.change) > 0 ? '+' : ''}{num(m.change)}</span>
                <span className="w-24 text-right tabular-nums text-muted">{num(m.balance_after)} {i.unit}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Sheet>
  )
}

function IngredientSheet({ ingredient, suppliers, onClose, onDone }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const isNew = !ingredient.id
  const [f, setF] = useState({ name: '', unit: 'g', low_stock_threshold: '0', supplier_id: '', is_active: true, ...ingredient,
    cost: ingredient.unit_cost_usd_millicents != null ? String(ingredient.unit_cost_usd_millicents / 100000) : '' })
  async function save() {
    const body = { name: f.name, unit: f.unit, low_stock_threshold: String(f.low_stock_threshold || 0), is_active: f.is_active,
      supplier_id: f.supplier_id ? Number(f.supplier_id) : null, unit_cost_usd_millicents: Math.round(Number(f.cost || 0) * 100000) }
    try {
      if (isNew) await staffApi('/api/admin/inventory/ingredients', { method: 'POST', body })
      else await staffApi(`/api/admin/inventory/ingredients/${ingredient.id}`, { method: 'PATCH', body })
      toast(t('admin.saved'))
      onDone()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  const bind = (k) => ({ value: f[k] ?? '', onChange: (e) => setF({ ...f, [k]: e.target.value }) })
  return (
    <Sheet open onClose={onClose} label={t('inv.ingredient')}>
      <div className="space-y-4 p-6">
        <h2 className="font-display text-2xl">{isNew ? t('inv.addIngredient') : ingredient.name}</h2>
        <Field label={t('inv.ingredient')}><input className={inputCls} {...bind('name')} /></Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t('inv.unit')} hint="g, kg, ml, l, pcs"><input className={inputCls} {...bind('unit')} /></Field>
          <Field label={t('inv.alertAt')}><input className={inputCls} inputMode="decimal" {...bind('low_stock_threshold')} /></Field>
        </div>
        <Field label={t('inv.costPerUnitUsd', { unit: f.unit || '…' })} hint={t('inv.costHint')}><input className={inputCls} inputMode="decimal" {...bind('cost')} placeholder="0.025" /></Field>
        <Field label={t('inv.supplier')}>
          <select className={inputCls} {...bind('supplier_id')}>
            <option value="">—</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        {isNew && <p className="text-xs text-muted">{t('inv.newStartsAtZero')}</p>}
        {!isNew && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('inv.active')}</label>}
        <Button variant="primary" size="lg" className="w-full" disabled={!f.name.trim() || !f.unit.trim()} onClick={save}>{t('admin.save')}</Button>
      </div>
    </Sheet>
  )
}

// ---------------------------------------------------------------- purchases
function Purchases({ ingredients, suppliers, editable, reload }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [list, setList] = useState(null)
  const [today] = useState(() => new Date().toLocaleDateString('en-CA'))
  const blank = { ingredient_id: '', quantity: '', total: '' }
  const [f, setF] = useState({ purchased_on: today, supplier_id: '', invoice_ref: '', lines: [blank] })
  const loadList = useCallback(() => staffApi('/api/admin/inventory/purchases').then(setList), [staffApi])
  useEffect(() => {
    loadList()
  }, [loadList])
  const setLine = (i, patch) => setF({ ...f, lines: f.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)) })
  const valid = f.lines.every((l) => l.ingredient_id && Number(l.quantity) > 0 && parseUsd(l.total) != null)
  const total = f.lines.reduce((s, l) => s + (parseUsd(l.total) ?? 0), 0)
  async function save() {
    try {
      await staffApi('/api/admin/inventory/purchases', { method: 'POST', body: {
        purchased_on: f.purchased_on, supplier_id: f.supplier_id ? Number(f.supplier_id) : null, invoice_ref: f.invoice_ref,
        lines: f.lines.map((l) => ({ ingredient_id: Number(l.ingredient_id), quantity: l.quantity, line_total_usd_cents: parseUsd(l.total) })) } })
      toast(t('inv.purchaseSaved'))
      setF({ purchased_on: today, supplier_id: '', invoice_ref: '', lines: [blank] })
      loadList()
      reload()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
      {editable && (
        <Card title={t('inv.newPurchase')}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label={t('inv.date')}><input type="date" className={inputCls} value={f.purchased_on} onChange={(e) => setF({ ...f, purchased_on: e.target.value })} /></Field>
              <Field label={t('inv.supplier')}>
                <select className={inputCls} value={f.supplier_id} onChange={(e) => setF({ ...f, supplier_id: e.target.value })}>
                  <option value="">—</option>
                  {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
            </div>
            <Field label={t('inv.invoice')}><input className={inputCls} value={f.invoice_ref} onChange={(e) => setF({ ...f, invoice_ref: e.target.value })} /></Field>
            <div className="space-y-2">
              {f.lines.map((l, i) => {
                const ing = ingredients.find((x) => String(x.id) === String(l.ingredient_id))
                return (
                  <div key={i} className="grid grid-cols-[1fr_90px_90px_auto] gap-2">
                    <select className={inputCls} value={l.ingredient_id} onChange={(e) => setLine(i, { ingredient_id: e.target.value })} aria-label={t('inv.ingredient')}>
                      <option value="">{t('inv.ingredient')}</option>
                      {ingredients.filter((x) => x.is_active).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                    </select>
                    <input className={inputCls} inputMode="decimal" placeholder={ing ? ing.unit : t('inv.qty')} value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} aria-label={t('inv.qty')} />
                    <input className={inputCls} inputMode="decimal" placeholder="$" value={l.total} onChange={(e) => setLine(i, { total: e.target.value })} aria-label={t('inv.lineTotal')} />
                    <button onClick={() => setF({ ...f, lines: f.lines.filter((_, j) => j !== i) })} disabled={f.lines.length === 1} className="text-muted hover:text-danger disabled:opacity-30" aria-label={t('admin.remove')}><Trash2 size={16} /></button>
                  </div>
                )
              })}
              <Button size="sm" variant="ghost" onClick={() => setF({ ...f, lines: [...f.lines, blank] })}><Plus size={14} /> {t('inv.addLine')}</Button>
            </div>
            <div className="flex items-center justify-between border-t border-line pt-3">
              <span className="text-sm text-muted">{t('cart.total')}</span>
              <span className="text-xl font-semibold tabular-nums">{formatUSD(total)}</span>
            </div>
            <Button variant="primary" size="lg" className="w-full" disabled={!valid} onClick={save}>{t('inv.savePurchase')}</Button>
            <p className="text-xs text-muted">{t('inv.purchaseHint')}</p>
          </div>
        </Card>
      )}
      <Card title={t('inv.recentPurchases')}>
        {!list ? <Skeleton className="h-40" /> : list.length === 0 ? <p className="text-sm text-muted">{t('inv.noPurchases')}</p> : (
          <ul className="-my-2 divide-y divide-line text-sm">
            {list.map((p) => (
              <li key={p.id} className="py-3">
                <div className="flex justify-between">
                  <span className="font-medium">{p.purchased_on} · {p.supplier || '—'}{p.invoice_ref && ` · ${p.invoice_ref}`}</span>
                  <span className="font-semibold tabular-nums">{formatUSD(p.total_usd_cents)}</span>
                </div>
                <div className="text-xs text-muted">{p.lines.map((l) => `${l.ingredient} ${num(l.quantity)} ${l.unit}`).join(' · ')}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- suppliers
function Suppliers({ suppliers, editable, reload }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [f, setF] = useState({ name: '', phone: '', contact_name: '' })
  async function add(e) {
    e.preventDefault()
    try {
      await staffApi('/api/admin/inventory/suppliers', { method: 'POST', body: f })
      setF({ name: '', phone: '', contact_name: '' })
      toast(t('admin.saved'))
      reload()
    } catch (err) {
      toast(err.message, 'bad')
    }
  }
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Card title={t('inv.tab.suppliers')}>
        {suppliers.length === 0 ? <p className="text-sm text-muted">—</p> : (
          <ul className="-my-2 divide-y divide-line text-sm">
            {suppliers.map((s) => (
              <li key={s.id} className="flex justify-between py-3"><span className="font-medium">{s.name}</span><span className="text-muted">{[s.contact_name, s.phone].filter(Boolean).join(' · ')}</span></li>
            ))}
          </ul>
        )}
      </Card>
      {editable && (
        <Card title={t('inv.addSupplier')}>
          <form onSubmit={add} className="space-y-3">
            <Field label={t('inv.supplierName')}><input required className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label={t('inv.contact')}><input className={inputCls} value={f.contact_name} onChange={(e) => setF({ ...f, contact_name: e.target.value })} /></Field>
            <Field label={t('inv.phone')}><input className={inputCls} value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
            <Button variant="primary" className="w-full"><Plus size={16} /> {t('inv.addSupplier')}</Button>
          </form>
        </Card>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- recipes
function Recipes({ ingredients, editable }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [menu, setMenu] = useState(null)
  const [productId, setProductId] = useState('')
  const [recipe, setRecipe] = useState(null)
  const [lines, setLines] = useState([])

  useEffect(() => {
    staffApi('/api/admin/menu').then(setMenu)
  }, [staffApi])
  useEffect(() => {
    if (!productId) return
    staffApi(`/api/admin/inventory/recipes/${productId}`).then((r) => {
      setRecipe(r)
      setLines(r.lines.map((l) => ({ ...l, option_id: l.option_id ?? '' })))
    })
  }, [productId, staffApi])

  const cost = useMemo(() => lines.reduce((s, l) => {
    const ing = ingredients.find((i) => String(i.id) === String(l.ingredient_id))
    return s + (ing && !l.option_id ? (Number(l.quantity) || 0) * ing.unit_cost_usd_millicents / 1000 : 0)
  }, 0), [lines, ingredients])

  async function save() {
    try {
      const r = await staffApi(`/api/admin/inventory/recipes/${productId}`, { method: 'PUT', body: lines.map((l) => ({
        ingredient_id: Number(l.ingredient_id), option_id: l.option_id ? Number(l.option_id) : null, quantity: String(l.quantity),
        scales_with_size: l.scales_with_size !== false })) })
      setRecipe(r)
      toast(t('admin.saved'))
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  const setLine = (i, patch) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const price = recipe?.product.price_usd_cents ?? 0

  return (
    <Card title={t('inv.tab.recipes')}>
      <p className="mb-4 text-sm text-muted">{t('inv.recipeHint')}</p>
      <select className={`${inputCls} max-w-sm`} value={productId} onChange={(e) => setProductId(e.target.value)} aria-label={t('admin.menu.product')}>
        <option value="">{t('inv.chooseProduct')}</option>
        {(menu?.categories ?? []).map((c) => (
          <optgroup key={c.id} label={c.name_en}>
            {menu.products.filter((p) => p.category_id === c.id && !p.is_archived).map((p) => <option key={p.id} value={p.id}>{p.name_en}</option>)}
          </optgroup>
        ))}
      </select>
      {recipe && (
        <div className="mt-5 space-y-3">
          {lines.map((l, i) => (
            <div key={i} className="grid grid-cols-2 items-center gap-2 sm:grid-cols-[1.4fr_1.4fr_100px_auto_auto]">
              <select className={inputCls} value={l.ingredient_id} onChange={(e) => setLine(i, { ingredient_id: e.target.value })} disabled={!editable} aria-label={t('inv.ingredient')}>
                <option value="">{t('inv.ingredient')}</option>
                {ingredients.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.unit})</option>)}
              </select>
              <select className={inputCls} value={l.option_id} onChange={(e) => setLine(i, { option_id: e.target.value })} disabled={!editable} aria-label={t('inv.whenUsed')}>
                <option value="">{t('inv.always')}</option>
                {recipe.options.map((o) => <option key={o.id} value={o.id}>{t('inv.onlyWith', { option: o.name })}</option>)}
              </select>
              <input className={inputCls} inputMode="decimal" value={l.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })} disabled={!editable} aria-label={t('inv.qty')} />
              <label className="flex items-center gap-1.5 text-xs" title={t('inv.scalesHint')}>
                <input type="checkbox" checked={l.scales_with_size !== false} disabled={!editable || !!l.option_id} onChange={(e) => setLine(i, { scales_with_size: e.target.checked })} /> {t('inv.scales')}
              </label>
              {editable && <button onClick={() => setLines(lines.filter((_, j) => j !== i))} className="text-muted hover:text-danger" aria-label={t('admin.remove')}><Trash2 size={16} /></button>}
            </div>
          ))}
          {editable && <Button size="sm" variant="ghost" onClick={() => setLines([...lines, { ingredient_id: '', option_id: '', quantity: '', scales_with_size: true }])}><Plus size={14} /> {t('inv.addIngredient')}</Button>}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-line pt-3 text-sm">
            <span>{t('inv.recipeCost')}: <b className="tabular-nums">{formatUSD(Math.round(cost))}</b></span>
            <span>{t('admin.menu.price')}: <b className="tabular-nums">{formatUSD(price)}</b></span>
            {price > 0 && <span>{t('inv.margin')}: <b className="tabular-nums">{Math.round((1 - cost / price) * 100)}%</b></span>}
          </div>
          {editable && <Button variant="primary" onClick={save} disabled={lines.some((l) => !l.ingredient_id || !(Number(l.quantity) > 0))}>{t('admin.save')}</Button>}
        </div>
      )}
    </Card>
  )
}
