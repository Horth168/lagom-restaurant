/* POS for the counter: fast product grid, cart, discounts, cash or KHQR, 80 mm receipt. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Banknote, CheckCircle2, History, LayoutDashboard, LogOut, Minus, Percent, Plus, Printer, Search, Trash2, X } from 'lucide-react'
import { KhqrCard } from '../../components/KhqrCard'
import { KhqrLogo } from '../../components/KhqrLogo'
import { Mark } from '../../components/Logo'
import { ProductImage } from '../../components/ProductImage'
import { Receipt, printSoon } from '../../components/Receipt'
import { Sheet } from '../../components/Sheet'
import { Badge, Button, Field, inputBase, inputCls, parseUsd, STATUS_TONE, ToastProvider, useToast } from '../../components/ui'
import { useI18n } from '../../i18n'
import { api } from '../../lib/api'
import { addLine, defaultSelection, itemCount, missingGroups, previewUnitPrice, selectedOptionIds, setQuantity, toggleOption } from '../../lib/cartMath'
import { formatKHR, formatUSD } from '../../lib/money'
import { useLiveChannel } from '../../lib/realtime'
import { useStaff } from '../../lib/staffAuth'
import { CashForm } from '../admin/Payments'
import { OrderDetail } from '../admin/Orders'

const newKey = () => (crypto.randomUUID ? crypto.randomUUID().replaceAll('-', '') : String(Date.now()) + Math.random().toString(16).slice(2))

export default function PosApp() {
  return (
    <ToastProvider>
      <Pos />
    </ToastProvider>
  )
}

function Pos() {
  const { t, pick } = useI18n()
  const { staffApi, can, user, logout, token } = useStaff()
  const toast = useToast()
  const [menu, setMenu] = useState(null)
  const [settings, setSettings] = useState(null)
  const [tables, setTables] = useState([])
  const [cat, setCat] = useState('all')
  const [query, setQuery] = useState('')
  const [lines, setLines] = useState([])
  const [mode, setMode] = useState('POS_TAKEAWAY')
  const [tableId, setTableId] = useState('')
  const [note, setNote] = useState('')
  const [discount, setDiscount] = useState(null) // {type:'percent'|'amount', value, reason}
  const [quote, setQuote] = useState(null)
  const [picking, setPicking] = useState(null)
  const [order, setOrder] = useState(null) // order being charged
  const [stage, setStage] = useState(null) // 'cash' | 'khqr' | 'done'
  const [khqr, setKhqr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [key, setKey] = useState(newKey)

  useEffect(() => {
    Promise.all([api('/api/public/menu'), api('/api/settings/public'), staffApi('/api/pos/tables')]).then(([m, s, tb]) => {
      setMenu(m)
      setSettings(s)
      setTables(tb)
    })
  }, [staffApi])

  // Server prices the cart (the same rules as everywhere else)
  useEffect(() => {
    if (!lines.length) {
      setQuote(null)
      return
    }
    const id = setTimeout(() => {
      api('/api/public/cart/quote', { method: 'POST', body: { items: lines.map(({ product_id, option_ids, quantity, special_instructions }) => ({ product_id, option_ids, quantity, special_instructions })) } })
        .then(setQuote)
        .catch((e) => toast(e.message, 'bad'))
    }, 150)
    return () => clearTimeout(id)
  }, [lines, toast])

  const productsById = useMemo(() => new Map((menu?.products ?? []).map((p) => [p.id, p])), [menu])
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (menu?.products ?? []).filter(
      (p) => (cat === 'all' || p.category_id === cat) && (!q || Object.values(p.name).some((n) => n.toLowerCase().includes(q))),
    )
  }, [menu, cat, query])

  const subtotal = quote?.subtotal_usd_cents ?? 0
  const discountCents = !discount ? 0 : discount.type === 'percent' ? Math.round((subtotal * Math.min(100, Number(discount.value) || 0)) / 100) : Math.min(subtotal, parseUsd(discount.value) ?? 0)
  const total = Math.max(0, subtotal - discountCents)

  function tapProduct(p) {
    if (!p.is_available) return
    if (p.option_groups.length) setPicking(p)
    else setLines((ls) => addLine(ls, { product_id: p.id, option_ids: [], special_instructions: '', quantity: 1 }))
  }

  function reset() {
    setLines([])
    setNote('')
    setDiscount(null)
    setOrder(null)
    setStage(null)
    setKhqr(null)
    setKey(newKey())
  }

  async function createOrder() {
    if (order) return order
    const body = {
      channel: mode, table_id: mode === 'POS_DINE_IN' ? Number(tableId) : null, customer_note: note, idempotency_key: key,
      items: lines.map(({ product_id, option_ids, quantity, special_instructions }) => ({ product_id, option_ids, quantity, special_instructions })),
      ...(discountCents ? { discount_reason: discount.reason, ...(discount.type === 'percent' ? { discount_percent: Number(discount.value) } : { discount_usd_cents: discountCents }) } : {}),
    }
    const o = await staffApi('/api/pos/orders', { method: 'POST', body })
    setOrder(o)
    return o
  }

  async function charge(kind) {
    setBusy(true)
    try {
      const o = await createOrder()
      if (kind === 'khqr') {
        setKhqr(await staffApi(`/api/pos/orders/${o.public_id}/khqr`, { method: 'POST', body: { currency: 'USD' } }))
      }
      setStage(kind)
    } catch (e) {
      toast(e.message, 'bad')
    } finally {
      setBusy(false)
    }
  }

  const finish = useCallback(async () => {
    if (!order) return
    const o = await staffApi(`/api/admin/orders/${order.public_id}`)
    setOrder(o)
    if (o.status !== 'PENDING_PAYMENT' && o.status !== 'EXPIRED') setStage('done')
  }, [order, staffApi])

  // KHQR on the counter: ABA's notice confirms it, the live update tells this screen
  useLiveChannel('/api/ws/staff', { token, station: null }, (msg) => {
    if (stage === 'khqr' && (msg.type === 'reconnected' || msg.order === order?.public_id)) finish()
  }, stage === 'khqr')

  const canCharge = lines.length > 0 && quote && (mode === 'POS_TAKEAWAY' || tableId) && !busy && (!discount || discount.reason?.trim())

  if (!menu) return <div className="grid min-h-dvh place-items-center"><Mark size={56} className="text-brand" /></div>

  return (
    <div className="flex h-dvh flex-col bg-bg md:flex-row">
      {/* ---------------------------------------------------------- products */}
      <section className="flex min-h-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line px-4 py-3">
          <Mark size={30} className="text-brand" />
          <label className="relative flex-1">
            <Search size={16} className="absolute top-3 left-3 text-muted" />
            <input className={`${inputCls} pl-9`} placeholder={t('menu.search')} value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <Button variant="ghost" onClick={() => setHistoryOpen(true)} title={t('pos.history')}><History size={18} /></Button>
          {can('dashboard.view') && <Link to="/admin" className="grid size-10 place-items-center rounded-lg hover:bg-surface-2" title="Admin"><LayoutDashboard size={18} /></Link>}
          <Button variant="ghost" onClick={logout} title={`${t('kds.signOut')} (${user?.full_name})`}><LogOut size={18} /></Button>
        </header>
        <nav className="no-scrollbar flex gap-2 overflow-x-auto border-b border-line px-4 py-2">
          {[{ id: 'all', name: { en: t('pos.all') } }, ...menu.categories].map((c) => (
            <button key={c.id} onClick={() => setCat(c.id)} className={`shrink-0 rounded-full px-4 py-2 text-sm ${cat === c.id ? 'bg-brand text-on-brand' : 'border border-line bg-surface'}`}>
              {pick(c.name)}
            </button>
          ))}
        </nav>
        <div className="grid flex-1 auto-rows-min gap-3 overflow-y-auto p-4 [grid-template-columns:repeat(auto-fill,minmax(150px,1fr))]">
          {shown.map((p) => (
            <button key={p.id} onClick={() => tapProduct(p)} disabled={!p.is_available}
              className="overflow-hidden rounded-xl border border-line bg-surface text-left transition active:scale-[0.98] disabled:opacity-45">
              <ProductImage src={p.image_url} alt={pick(p.name)} categorySlug={menu.categories.find((c) => c.id === p.category_id)?.slug} className="aspect-[4/3] w-full" />
              <div className="p-3">
                <div className="line-clamp-2 text-sm font-medium leading-snug">{pick(p.name)}</div>
                <div className="mt-1 text-sm font-semibold text-accent">{p.is_available ? formatUSD(p.price_usd_cents) : t('menu.soldOut')}</div>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- order */}
      <aside className="flex max-h-[55dvh] w-full flex-col border-t border-line bg-surface md:max-h-none md:w-[380px] md:border-t-0 md:border-l">
        <div className="grid grid-cols-2 gap-2 p-4 pb-2">
          {['POS_TAKEAWAY', 'POS_DINE_IN'].map((m) => (
            <button key={m} onClick={() => setMode(m)} className={`h-10 rounded-lg text-sm font-semibold ${mode === m ? 'bg-brand text-on-brand' : 'border border-line'}`}>{t(`channel.${m}`)}</button>
          ))}
        </div>
        {mode === 'POS_DINE_IN' && (
          <div className="px-4 pb-2">
            <select className={inputCls} value={tableId} onChange={(e) => setTableId(e.target.value)} aria-label={t('track.table')}>
              <option value="">{t('pos.chooseTable')}</option>
              {tables.map((tb) => <option key={tb.id} value={tb.id}>{tb.label}{tb.area && ` · ${tb.area}`}</option>)}
            </select>
          </div>
        )}
        <ul className="flex-1 divide-y divide-line overflow-y-auto px-4">
          {lines.length === 0 && <li className="py-10 text-center text-sm text-muted">{t('pos.empty')}</li>}
          {lines.map((l, i) => {
            const p = productsById.get(l.product_id)
            const q = quote?.lines[i]
            return (
              <li key={l.key} className="py-3">
                <div className="flex justify-between gap-2 text-sm">
                  <span className="font-medium">{p ? pick(p.name) : ''}</span>
                  <span className="tabular-nums">{q ? formatUSD(q.line_total_usd_cents) : ''}</span>
                </div>
                {q?.options.length > 0 && <div className="text-xs text-muted">{q.options.map((o) => o.name_en).join(' · ')}</div>}
                <div className="mt-2 flex items-center gap-2">
                  <button className="grid size-8 place-items-center rounded-full border border-line" onClick={() => setLines((ls) => setQuantity(ls, l.key, l.quantity - 1))} aria-label={t('product.decrease')}><Minus size={14} /></button>
                  <span className="w-6 text-center font-semibold tabular-nums">{l.quantity}</span>
                  <button className="grid size-8 place-items-center rounded-full border border-line" onClick={() => setLines((ls) => setQuantity(ls, l.key, l.quantity + 1))} aria-label={t('product.increase')}><Plus size={14} /></button>
                  <button className="ml-auto text-muted hover:text-danger" onClick={() => setLines((ls) => setQuantity(ls, l.key, 0))} aria-label={t('admin.remove')}><Trash2 size={16} /></button>
                </div>
              </li>
            )
          })}
        </ul>
        <div className="space-y-2 border-t border-line p-4">
          <input className={inputCls} placeholder={t('cart.note')} value={note} onChange={(e) => setNote(e.target.value)} />
          {can('orders.discount') && (
            discount ? (
              <div className="space-y-2 rounded-lg bg-surface-2 p-3">
                <div className="flex gap-2">
                  <select aria-label={t('pos.discount')} className={`${inputBase} w-24`} value={discount.type} onChange={(e) => setDiscount({ ...discount, type: e.target.value })}>
                    <option value="percent">%</option>
                    <option value="amount">$</option>
                  </select>
                  <input className={inputCls} inputMode="decimal" value={discount.value} onChange={(e) => setDiscount({ ...discount, value: e.target.value })} placeholder={discount.type === 'percent' ? '10' : '1.00'} aria-label={t('pos.discount')} />
                  <button onClick={() => setDiscount(null)} aria-label={t('admin.remove')}><X size={18} /></button>
                </div>
                <input className={inputCls} placeholder={t('pos.discountReason')} value={discount.reason} onChange={(e) => setDiscount({ ...discount, reason: e.target.value })} />
              </div>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setDiscount({ type: 'percent', value: '', reason: '' })} disabled={!lines.length}><Percent size={14} /> {t('pos.discount')}</Button>
            )
          )}
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between text-muted"><dt>{t('cart.subtotal')} · {itemCount(lines)}</dt><dd className="tabular-nums">{formatUSD(subtotal)}</dd></div>
            {discountCents > 0 && <div className="flex justify-between text-muted"><dt>{t('pos.discount')}</dt><dd className="tabular-nums">-{formatUSD(discountCents)}</dd></div>}
            <div className="flex justify-between text-xl font-semibold"><dt>{t('cart.total')}</dt><dd className="tabular-nums">{formatUSD(total)}</dd></div>
            <div className="flex justify-between text-muted"><dt /><dd className="tabular-nums">{settings && formatKHR(Math.floor((total * Number(settings.khr_per_usd)) / 10000 + 0.5) * 100)}</dd></div>
          </dl>
          <div className="grid grid-cols-2 gap-2 pt-1">
            <Button variant="primary" size="lg" disabled={!canCharge} onClick={() => charge('cash')} className="h-14"><Banknote size={18} /> {t('pos.cash')}</Button>
            <Button size="lg" disabled={!canCharge} onClick={() => charge('khqr')} className="h-14 border-[#E1232E]/40 bg-white text-[#E1232E]"><KhqrLogo height={14} /></Button>
          </div>
        </div>
      </aside>

      {picking && <OptionPicker product={picking} onClose={() => setPicking(null)} onAdd={(line) => { setLines((ls) => addLine(ls, line)); setPicking(null) }} />}

      {/* ---------------------------------------------------------- charge */}
      <Sheet open={!!stage} onClose={() => (stage === 'done' ? reset() : setStage(null))} label={t('pos.charge')}>
        <div className="p-6">
          {order && stage !== 'done' && (
            <div className="mb-4 flex items-baseline justify-between pr-10">
              <h2 className="font-display text-2xl">{t('pay.order', { n: order.number })}</h2>
              <span className="text-2xl font-semibold tabular-nums">{formatUSD(order.total_usd_cents)}</span>
            </div>
          )}
          {stage === 'cash' && order && <CashForm order={order} onDone={finish} />}
          {stage === 'khqr' && khqr && (
            <div className="flex flex-col items-center gap-4">
              <KhqrCard qrString={khqr.qr_string} amountMinor={khqr.amount_minor} currency={khqr.currency} />
              <p className="text-center text-sm text-muted">{t('pos.khqrHint')}</p>
              <Button variant="ghost" onClick={() => setStage('cash')}><Banknote size={16} /> {t('pos.switchCash')}</Button>
            </div>
          )}
          {stage === 'done' && order && (
            <div className="flex flex-col items-center gap-4 py-4 text-center">
              <CheckCircle2 size={56} className="text-series-1" />
              <h2 className="font-display text-3xl">{t('pos.paid', { n: order.number })}</h2>
              {order.payments.find((p) => p.status === 'APPROVED')?.change_given_minor > 0 && (
                <p className="text-xl">{t('pos.change')}: <b className="tabular-nums">{(() => { const p = order.payments.find((x) => x.status === 'APPROVED'); return p.currency === 'KHR' ? formatKHR(p.change_given_minor) : formatUSD(p.change_given_minor) })()}</b></p>
              )}
              <div className="flex gap-2">
                <Button onClick={printSoon}><Printer size={16} /> {t('admin.printReceipt')}</Button>
                <Button variant="primary" onClick={reset}>{t('pos.newOrder')}</Button>
              </div>
              <Receipt order={order} />
            </div>
          )}
        </div>
      </Sheet>
      <PosHistory open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </div>
  )
}

function OptionPicker({ product, onClose, onAdd }) {
  const { t, pick } = useI18n()
  const [sel, setSel] = useState(() => defaultSelection(product))
  const [notes, setNotes] = useState('')
  const missing = missingGroups(product, sel)
  return (
    <Sheet open onClose={onClose} label={pick(product.name)}>
      <div className="p-6">
        <h2 className="pr-10 font-display text-2xl">{pick(product.name)}</h2>
        {product.option_groups.map((g) => (
          <div key={g.id} className="mt-5">
            <div className="text-sm font-semibold">{pick(g.name)} {g.min_select > 0 && <span className="text-xs font-normal text-muted">· {t('product.required')}</span>}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {g.options.map((o) => {
                const on = (sel[g.id] || []).includes(o.id)
                return (
                  <button key={o.id} disabled={!o.is_available} onClick={() => setSel((s) => toggleOption(g, s, o.id))}
                    className={`min-h-11 rounded-full border px-4 text-sm disabled:opacity-40 ${on ? 'border-brand bg-brand text-on-brand' : 'border-line'}`}>
                    {pick(o.name)}{o.price_delta_usd_cents ? ` +${formatUSD(o.price_delta_usd_cents)}` : ''}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        {product.allow_special_instructions && (
          <div className="mt-5"><Field label={t('product.instructions')}><input className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field></div>
        )}
        <Button variant="primary" size="lg" className="mt-6 w-full" disabled={missing.length > 0}
          onClick={() => onAdd({ product_id: product.id, option_ids: selectedOptionIds(product, sel), special_instructions: notes.trim(), quantity: 1 })}>
          {t('product.addToCart', { price: formatUSD(previewUnitPrice(product, sel)) })}
        </Button>
      </div>
    </Sheet>
  )
}

function PosHistory({ open, onClose }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const [data, setData] = useState(null)
  const [detail, setDetail] = useState(null)
  useEffect(() => {
    if (open) staffApi('/api/pos/history').then(setData)
  }, [open, staffApi])
  const paidTotal = (data?.orders ?? []).filter((o) => ['PAID', 'PREPARING', 'READY', 'SERVED'].includes(o.status)).reduce((s, o) => s + o.total_usd_cents, 0)
  return (
    <>
      <Sheet open={open && !detail} onClose={onClose} label={t('pos.history')}>
        <div className="p-6">
          <h2 className="font-display text-2xl">{t('pos.history')}</h2>
          <p className="text-sm text-muted">{t('pos.todayTotal')}: <b className="text-ink">{formatUSD(paidTotal)}</b></p>
          <ul className="mt-4 divide-y divide-line">
            {(data?.orders ?? []).map((o) => (
              <li key={o.public_id}>
                <button onClick={() => setDetail(o.public_id)} className="flex w-full items-center gap-3 py-3 text-left text-sm hover:bg-surface-2">
                  <span className="w-12 font-semibold tabular-nums">#{o.number}</span>
                  <span className="flex-1">{o.table || t(`channel.${o.channel}`)}<span className="block text-xs text-muted">{new Date(o.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {o.payment_method ? t(`pay.${o.payment_method}`) : '—'}</span></span>
                  <Badge tone={STATUS_TONE[o.status]}>{t(`status.${o.status}`)}</Badge>
                  <span className="w-16 text-right font-semibold tabular-nums">{formatUSD(o.total_usd_cents)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </Sheet>
      <OrderDetail publicId={detail} onClose={() => setDetail(null)} />
    </>
  )
}
