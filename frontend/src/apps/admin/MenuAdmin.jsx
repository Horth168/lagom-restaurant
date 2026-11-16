import { useCallback, useEffect, useMemo, useState } from 'react'
import { ImagePlus, Plus, Trash2 } from 'lucide-react'
import { ProductImage } from '../../components/ProductImage'
import { Sheet } from '../../components/Sheet'
import { Badge, Button, Card, centsToInput, Field, inputCls, parseUsd, Skeleton, useToast } from '../../components/ui'
import { useI18n } from '../../i18n'
import { formatUSD } from '../../lib/money'
import { useStaff } from '../../lib/staffAuth'
import { PageTitle } from './AdminApp'

const STATIONS = ['KITCHEN', 'DRINKS', 'DESSERT']

export default function MenuAdmin() {
  const { t } = useI18n()
  const { staffApi, can } = useStaff()
  const toast = useToast()
  const [menu, setMenu] = useState(null)
  const [catId, setCatId] = useState(null)
  const [editing, setEditing] = useState(null) // product object or {new: true}
  const [showArchived, setShowArchived] = useState(false)
  const [catForm, setCatForm] = useState(null)
  const editable = can('menu.edit')

  const load = useCallback(async () => {
    const m = await staffApi('/api/admin/menu')
    setMenu(m)
    setCatId((c) => c ?? m.categories[0]?.id)
  }, [staffApi])

  useEffect(() => {
    load()
  }, [load])

  async function patch(p, body, message) {
    try {
      await staffApi(`/api/admin/products/${p.id}`, { method: 'PATCH', body })
      toast(message)
      load()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  const products = useMemo(
    () => (menu?.products ?? []).filter((p) => p.category_id === catId && (showArchived || !p.is_archived)),
    [menu, catId, showArchived],
  )

  if (!menu) return <Skeleton className="h-96" />

  return (
    <>
      <PageTitle title={t('admin.nav.menu')}>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> {t('admin.menu.showArchived')}
        </label>
        {editable && <Button variant="primary" onClick={() => setEditing({ new: true, category_id: catId })}><Plus size={16} /> {t('admin.menu.addProduct')}</Button>}
      </PageTitle>
      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <Card title={t('admin.menu.categories')} action={editable && <Button size="sm" variant="ghost" onClick={() => setCatForm({})}><Plus size={14} /></Button>}>
          <ul className="-m-2 space-y-0.5">
            {menu.categories.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => setCatId(c.id)}
                  onDoubleClick={() => editable && setCatForm(c)}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${c.id === catId ? 'bg-surface-2 font-semibold' : 'hover:bg-surface-2'}`}
                >
                  <span className={c.is_active ? '' : 'text-muted line-through'}>{c.name_en}</span>
                  <span className="text-xs text-muted">{menu.products.filter((p) => p.category_id === c.id && !p.is_archived).length}</span>
                </button>
              </li>
            ))}
          </ul>
          {editable && <p className="mt-3 text-xs text-muted">{t('admin.menu.categoryHint')}</p>}
        </Card>

        <Card>
          {products.length === 0 ? (
            <p className="py-10 text-center text-muted">{t('admin.menu.empty')}</p>
          ) : (
            <ul className="-my-2 divide-y divide-line">
              {products.map((p) => (
                <li key={p.id} className="flex items-center gap-4 py-3">
                  <ProductImage src={p.image_url} alt={p.name_en} categorySlug={menu.categories.find((c) => c.id === p.category_id)?.slug} className="size-14 shrink-0 rounded-lg" iconSize={20} />
                  <button className="min-w-0 flex-1 text-left" onClick={() => editable && setEditing(p)} disabled={!editable}>
                    <span className="block truncate font-medium">{p.name_en}</span>
                    <span className="block truncate text-sm text-muted">{p.name_km} · {p.name_zh}</span>
                    <span className="mt-1 flex flex-wrap gap-1">
                      <Badge>{t(`kds.station.${p.effective_station}`)}</Badge>
                      {p.is_archived && <Badge tone="neutral">{t('admin.menu.archived')}</Badge>}
                      {p.is_featured && <Badge tone="info">{t('menu.featured')}</Badge>}
                    </span>
                  </button>
                  <span className="w-16 text-right font-semibold tabular-nums">{formatUSD(p.price_usd_cents)}</span>
                  {editable && !p.is_archived && (
                    <button
                      onClick={() => patch(p, { is_available: !p.is_available }, p.is_available ? t('admin.menu.markedSoldOut') : t('admin.menu.markedAvailable'))}
                      className={`w-28 rounded-full px-3 py-1.5 text-xs font-semibold ${p.is_available ? 'bg-series-1/15 text-series-1' : 'bg-danger/15 text-danger'}`}
                      aria-pressed={p.is_available}
                    >
                      {p.is_available ? t('admin.menu.available') : t('menu.soldOut')}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      {editing && <ProductEditor product={editing} categories={menu.categories} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
      {catForm && <CategoryEditor category={catForm} onClose={() => setCatForm(null)} onSaved={() => { setCatForm(null); load() }} />}
    </>
  )
}

function CategoryEditor({ category, onClose, onSaved }) {
  const { t } = useI18n()
  const { staffApi } = useStaff()
  const toast = useToast()
  const [f, setF] = useState({ slug: '', name_en: '', name_km: '', name_zh: '', default_station: 'KITCHEN', is_active: true, sort_order: 0, ...category })
  const isNew = !category.id
  async function save() {
    try {
      if (isNew) await staffApi('/api/admin/categories', { method: 'POST', body: f })
      else {
        const { name_en, name_km, name_zh, default_station, is_active, sort_order } = f
        await staffApi(`/api/admin/categories/${category.id}`, { method: 'PATCH', body: { name_en, name_km, name_zh, default_station, is_active, sort_order } })
      }
      toast(t('admin.saved'))
      onSaved()
    } catch (e) {
      toast(e.message, 'bad')
    }
  }
  const bind = (k) => ({ value: f[k], onChange: (e) => setF({ ...f, [k]: e.target.value }) })
  return (
    <Sheet open onClose={onClose} label={t('admin.menu.category')}>
      <div className="space-y-4 p-6">
        <h2 className="font-display text-2xl">{t('admin.menu.category')}</h2>
        {isNew && <Field label={t('admin.menu.slug')} hint={t('admin.menu.slugHint')}><input className={inputCls} {...bind('slug')} /></Field>}
        <Field label="English"><input className={inputCls} {...bind('name_en')} /></Field>
        <Field label="ខ្មែរ"><input className={inputCls} lang="km" {...bind('name_km')} /></Field>
        <Field label="中文"><input className={inputCls} lang="zh" {...bind('name_zh')} /></Field>
        <Field label={t('admin.menu.station')}>
          <select className={inputCls} {...bind('default_station')}>{STATIONS.map((s) => <option key={s} value={s}>{t(`kds.station.${s}`)}</option>)}</select>
        </Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> {t('admin.menu.visible')}</label>
        <Button variant="primary" onClick={save} disabled={!f.name_en.trim() || (isNew && !f.slug)}>{t('admin.save')}</Button>
      </div>
    </Sheet>
  )
}

const emptyOption = () => ({ name_en: '', name_km: '', name_zh: '', price_delta_usd_cents: 0, is_default: false, is_available: true })

function ProductEditor({ product, categories, onClose, onSaved }) {
  const { t } = useI18n()
  const { staffApi, token } = useStaff()
  const toast = useToast()
  const isNew = !!product.new
  const [f, setF] = useState(() => ({
    category_id: product.category_id ?? categories[0]?.id, name_en: '', name_km: '', name_zh: '',
    description_en: '', description_km: '', description_zh: '', station: null, prep_minutes: 10,
    is_available: true, is_featured: false, is_best_seller: false, allow_special_instructions: true, is_archived: false,
    option_groups: [], ...product,
  }))
  const [price, setPrice] = useState(isNew ? '' : centsToInput(product.price_usd_cents))
  const [busy, setBusy] = useState(false)
  const bind = (k) => ({ value: f[k] ?? '', onChange: (e) => setF({ ...f, [k]: e.target.value }) })
  const cents = parseUsd(price)

  const setGroup = (gi, patch) => setF({ ...f, option_groups: f.option_groups.map((g, i) => (i === gi ? { ...g, ...patch } : g)) })
  const setOption = (gi, oi, patch) =>
    setGroup(gi, { options: f.option_groups[gi].options.map((o, i) => (i === oi ? { ...o, ...patch } : o)) })

  async function save() {
    setBusy(true)
    const body = {
      category_id: Number(f.category_id), name_en: f.name_en, name_km: f.name_km, name_zh: f.name_zh,
      description_en: f.description_en, description_km: f.description_km, description_zh: f.description_zh,
      price_usd_cents: cents, station: f.station || null, prep_minutes: Number(f.prep_minutes) || 0,
      is_available: f.is_available, is_featured: f.is_featured, is_best_seller: f.is_best_seller,
      allow_special_instructions: f.allow_special_instructions,
      option_groups: f.option_groups.map((g) => ({
        id: g.id, name_en: g.name_en, name_km: g.name_km || '', name_zh: g.name_zh || '', selection: g.selection,
        is_required: g.is_required, max_select: Number(g.max_select) || 1,
        options: g.options.map((o) => ({ id: o.id, name_en: o.name_en, name_km: o.name_km || '', name_zh: o.name_zh || '',
          price_delta_usd_cents: o.price_delta_usd_cents, is_default: o.is_default, is_available: o.is_available })),
      })),
    }
    if (!isNew) body.is_archived = f.is_archived
    try {
      const saved = isNew
        ? await staffApi('/api/admin/products', { method: 'POST', body })
        : await staffApi(`/api/admin/products/${product.id}`, { method: 'PATCH', body })
      toast(t('admin.saved'))
      onSaved(saved)
    } catch (e) {
      toast(typeof e.detail === 'object' && Array.isArray(e.detail) ? t('admin.checkFields') : e.message, 'bad')
      setBusy(false)
    }
  }

  async function upload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || ''}/api/admin/products/${product.id}/photo`, {
        method: 'POST', body: form, headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setF((x) => ({ ...x, image_url: data.image_url }))
      toast(t('admin.menu.photoSaved'))
    } catch (err) {
      toast(err.message, 'bad')
    }
  }

  return (
    <Sheet open onClose={onClose} label={t('admin.menu.product')}>
      <div className="space-y-5 p-6">
        <h2 className="font-display text-2xl">{isNew ? t('admin.menu.addProduct') : f.name_en}</h2>
        {!isNew && (
          <div className="flex items-center gap-4">
            <ProductImage src={f.image_url} alt={f.name_en} className="size-24 rounded-xl" />
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm hover:bg-surface-2">
              <ImagePlus size={16} /> {t('admin.menu.uploadPhoto')}
              <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={upload} />
            </label>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('admin.menu.category')}>
            <select className={inputCls} {...bind('category_id')}>{categories.map((c) => <option key={c.id} value={c.id}>{c.name_en}</option>)}</select>
          </Field>
          <Field label={t('admin.menu.price')} hint={price && cents == null ? t('admin.menu.priceHint') : undefined}>
            <input className={inputCls} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" />
          </Field>
        </div>
        <Field label="Name · English"><input className={inputCls} {...bind('name_en')} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="ឈ្មោះ · ខ្មែរ"><input className={inputCls} lang="km" {...bind('name_km')} /></Field>
          <Field label="名称 · 中文"><input className={inputCls} lang="zh" {...bind('name_zh')} /></Field>
        </div>
        <Field label="Description · English"><textarea rows={2} className={`${inputCls} h-auto py-2`} {...bind('description_en')} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="ពិពណ៌នា · ខ្មែរ"><textarea rows={2} lang="km" className={`${inputCls} h-auto py-2`} {...bind('description_km')} /></Field>
          <Field label="描述 · 中文"><textarea rows={2} lang="zh" className={`${inputCls} h-auto py-2`} {...bind('description_zh')} /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('admin.menu.station')} hint={t('admin.menu.stationHint')}>
            <select className={inputCls} value={f.station || ''} onChange={(e) => setF({ ...f, station: e.target.value || null })}>
              <option value="">{t('admin.menu.fromCategory')}</option>
              {STATIONS.map((s) => <option key={s} value={s}>{t(`kds.station.${s}`)}</option>)}
            </select>
          </Field>
          <Field label={t('admin.menu.prepMinutes')}><input type="number" min="0" max="180" className={inputCls} {...bind('prep_minutes')} /></Field>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {[['is_available', 'admin.menu.available'], ['is_featured', 'menu.featured'], ['is_best_seller', 'menu.bestSeller'], ['allow_special_instructions', 'product.instructions'], ...(isNew ? [] : [['is_archived', 'admin.menu.archived']])].map(([k, label]) => (
            <label key={k} className="flex items-center gap-2"><input type="checkbox" checked={!!f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} /> {t(label)}</label>
          ))}
        </div>

        <div>
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">{t('admin.menu.options')}</h3>
            <Button size="sm" onClick={() => setF({ ...f, option_groups: [...f.option_groups, { name_en: '', selection: 'SINGLE', is_required: false, max_select: 1, options: [emptyOption()] }] })}>
              <Plus size={14} /> {t('admin.menu.addGroup')}
            </Button>
          </div>
          <p className="mt-1 text-xs text-muted">{t('admin.menu.optionsHint')}</p>
          <div className="mt-3 space-y-4">
            {f.option_groups.map((g, gi) => (
              <div key={g.id ?? `n${gi}`} className="rounded-xl border border-line p-4">
                <div className="flex flex-wrap items-end gap-3">
                  <Field label={t('admin.menu.groupName')}><input className={inputCls} value={g.name_en} onChange={(e) => setGroup(gi, { name_en: e.target.value })} placeholder="Size" /></Field>
                  <Field label={t('admin.menu.choice')}>
                    <select className={inputCls} value={g.selection} onChange={(e) => setGroup(gi, { selection: e.target.value })}>
                      <option value="SINGLE">{t('product.chooseOne')}</option>
                      <option value="MULTIPLE">{t('admin.menu.multiple')}</option>
                    </select>
                  </Field>
                  {g.selection === 'MULTIPLE' && <Field label={t('admin.menu.max')}><input type="number" min="1" max="20" className={`${inputCls} w-20`} value={g.max_select} onChange={(e) => setGroup(gi, { max_select: e.target.value })} /></Field>}
                  <label className="mb-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={g.is_required} onChange={(e) => setGroup(gi, { is_required: e.target.checked })} /> {t('product.required')}</label>
                  <button onClick={() => setF({ ...f, option_groups: f.option_groups.filter((_, i) => i !== gi) })} className="mb-2 ml-auto text-muted hover:text-danger" aria-label={t('admin.remove')}><Trash2 size={16} /></button>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_1fr_90px_auto_auto]">
                  {g.options.map((o, oi) => (
                    <div key={o.id ?? `o${oi}`} className="col-span-2 grid grid-cols-2 gap-2 sm:col-span-6 sm:grid-cols-[1fr_1fr_1fr_90px_auto_auto] sm:items-center">
                      <input className={inputCls} placeholder="English" value={o.name_en} onChange={(e) => setOption(gi, oi, { name_en: e.target.value })} />
                      <input className={inputCls} lang="km" placeholder="ខ្មែរ" value={o.name_km || ''} onChange={(e) => setOption(gi, oi, { name_km: e.target.value })} />
                      <input className={inputCls} lang="zh" placeholder="中文" value={o.name_zh || ''} onChange={(e) => setOption(gi, oi, { name_zh: e.target.value })} />
                      <input className={inputCls} inputMode="decimal" placeholder="+0.00" defaultValue={o.price_delta_usd_cents ? centsToInput(o.price_delta_usd_cents) : ''}
                        onBlur={(e) => setOption(gi, oi, { price_delta_usd_cents: parseUsd(e.target.value || '0') ?? 0 })} aria-label={t('admin.menu.extraPrice')} />
                      <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={o.is_default} onChange={(e) => setOption(gi, oi, { is_default: e.target.checked })} /> {t('admin.menu.default')}</label>
                      <button onClick={() => setGroup(gi, { options: g.options.filter((_, i) => i !== oi) })} className="text-muted hover:text-danger" aria-label={t('admin.remove')} disabled={g.options.length === 1}><Trash2 size={15} /></button>
                    </div>
                  ))}
                </div>
                <Button size="sm" variant="ghost" className="mt-2" onClick={() => setGroup(gi, { options: [...g.options, emptyOption()] })}><Plus size={14} /> {t('admin.menu.addOption')}</Button>
              </div>
            ))}
          </div>
        </div>

        <div className="sticky bottom-0 -mx-6 border-t border-line bg-surface px-6 py-4">
          <Button variant="primary" size="lg" className="w-full" onClick={save} disabled={busy || !f.name_en.trim() || cents == null}>{t('admin.save')}</Button>
        </div>
      </div>
    </Sheet>
  )
}
