import { useState } from 'react'
import { Check, Clock, Minus, Plus } from 'lucide-react'
import { ProductImage } from '../../components/ProductImage'
import { Sheet } from '../../components/Sheet'
import { useI18n } from '../../i18n'
import { formatPrice, formatUSD } from '../../lib/money'
import { defaultSelection, missingGroups, previewUnitPrice, selectedOptionIds, toggleOption } from '../../lib/cartMath'
import { useCustomer } from './CustomerContext'

export function ProductSheet({ product, onClose }) {
  const { pick } = useI18n()
  return (
    <Sheet open={!!product} onClose={onClose} label={product ? pick(product.name) : ''}>
      {/* key resets the choices whenever a different product opens */}
      {product && <ProductForm key={product.id} product={product} onDone={onClose} />}
    </Sheet>
  )
}

function ProductForm({ product, onDone }) {
  const { t, pick } = useI18n()
  const { add, settings, categoriesById } = useCustomer()
  const [selected, setSelected] = useState(() => defaultSelection(product))
  const [qty, setQty] = useState(1)
  const [notes, setNotes] = useState('')
  const [showMissing, setShowMissing] = useState(false)

  const missing = missingGroups(product, selected)
  const unit = previewUnitPrice(product, selected)
  const total = formatPrice(unit * qty, settings).primary

  const submit = () => {
    if (missing.length) {
      setShowMissing(true)
      document.getElementById(`group-${missing[0].id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      return
    }
    add({
      product_id: product.id,
      option_ids: selectedOptionIds(product, selected),
      special_instructions: notes.trim(),
      quantity: qty,
    })
    onDone()
  }

  return (
    <div className="flex flex-col">
      <ProductImage
        src={product.image_url}
        alt={pick(product.name)}
        categorySlug={categoriesById.get(product.category_id)?.slug}
        className="aspect-[16/10] w-full"
        iconSize={56}
      />
      <div className="px-5 pt-5">
        <h2 className="font-display text-[28px] leading-tight">{pick(product.name)}</h2>
        {pick(product.description) && <p className="mt-2 text-[15px] text-muted">{pick(product.description)}</p>}
        <div className="mt-3 flex items-center gap-3 text-sm text-muted">
          <span className="font-semibold text-ink">{formatPrice(product.price_usd_cents, settings).primary}</span>
          <span className="inline-flex items-center gap-1">
            <Clock size={14} /> {t('product.prep', { n: product.prep_minutes })}
          </span>
        </div>
      </div>

      {product.option_groups.map((g) => {
        const picks = selected[g.id] || []
        const isMissing = showMissing && picks.length < g.min_select
        return (
          <fieldset key={g.id} id={`group-${g.id}`} className="mt-6 border-t border-line px-5 pt-5">
            <legend className="sr-only">{pick(g.name)}</legend>
            <div className="flex items-baseline justify-between">
              <h3 className="text-[17px] font-semibold">{pick(g.name)}</h3>
              <span className={`text-xs font-medium ${isMissing ? 'text-danger' : 'text-muted'}`}>
                {g.min_select > 0 ? t('product.required') : t('product.optional')}
                {' · '}
                {g.selection === 'SINGLE' ? t('product.chooseOne') : t('product.chooseUpTo', { n: g.max_select })}
              </span>
            </div>
            <div className={`mt-3 ${g.selection === 'SINGLE' && g.options.length <= 5 ? 'flex flex-wrap gap-2' : 'divide-y divide-line'}`}>
              {g.options.map((o) => {
                const on = picks.includes(o.id)
                const disabled = !o.is_available || (!on && g.selection === 'MULTIPLE' && picks.length >= g.max_select)
                const delta = o.price_delta_usd_cents ? `+${formatUSD(o.price_delta_usd_cents)}` : ''
                if (g.selection === 'SINGLE' && g.options.length <= 5) {
                  return (
                    <button
                      key={o.id}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      disabled={disabled}
                      onClick={() => setSelected((s) => toggleOption(g, s, o.id))}
                      className={`min-h-11 rounded-full border px-4 text-[15px] transition-colors disabled:opacity-40 ${
                        on ? 'border-brand bg-brand text-on-brand' : 'border-line bg-surface text-ink'
                      }`}
                    >
                      {pick(o.name)}
                      {delta && <span className={`ml-1.5 text-xs ${on ? 'opacity-80' : 'text-muted'}`}>{delta}</span>}
                    </button>
                  )
                }
                return (
                  <button
                    key={o.id}
                    type="button"
                    role={g.selection === 'SINGLE' ? 'radio' : 'checkbox'}
                    aria-checked={on}
                    disabled={disabled}
                    onClick={() => setSelected((s) => toggleOption(g, s, o.id))}
                    className="flex min-h-12 w-full items-center gap-3 py-2 text-left text-[15px] disabled:opacity-40"
                  >
                    <span
                      className={`grid size-6 shrink-0 place-items-center border transition-colors ${
                        g.selection === 'SINGLE' ? 'rounded-full' : 'rounded-md'
                      } ${on ? 'border-brand bg-brand text-on-brand' : 'border-line'}`}
                    >
                      {on && <Check size={15} strokeWidth={2.5} />}
                    </span>
                    <span className="flex-1">{pick(o.name)}</span>
                    {delta && <span className="text-sm text-muted">{delta}</span>}
                  </button>
                )
              })}
            </div>
          </fieldset>
        )
      })}

      {product.allow_special_instructions && (
        <div className="mt-6 border-t border-line px-5 pt-5">
          <label htmlFor="notes" className="text-[17px] font-semibold">
            {t('product.instructions')} <span className="text-xs font-medium text-muted">· {t('product.optional')}</span>
          </label>
          <textarea
            id="notes"
            value={notes}
            maxLength={255}
            onChange={(e) => setNotes(e.target.value)}
            placeholder={t('product.instructionsPlaceholder')}
            rows={2}
            className="mt-3 w-full resize-none rounded-xl border border-line bg-surface p-3 text-[16px] outline-none placeholder:text-muted focus:border-accent"
          />
        </div>
      )}

      <div className="sticky bottom-0 mt-6 flex items-center gap-3 border-t border-line bg-surface px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <Stepper value={qty} onChange={setQty} />
        <button
          onClick={submit}
          disabled={!product.is_available}
          className="h-12 flex-1 rounded-full bg-brand px-4 text-[15px] font-semibold text-on-brand disabled:opacity-40"
        >
          {product.is_available ? t('product.addToCart', { price: total }) : t('product.unavailable')}
        </button>
      </div>
    </div>
  )
}

export function Stepper({ value, onChange, min = 1, max = 50, size = 'md', labelledBy }) {
  const { t } = useI18n()
  const s = size === 'sm' ? 'size-8' : 'size-11'
  return (
    <div className="flex items-center rounded-full border border-line" aria-labelledby={labelledBy}>
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        disabled={value <= min}
        className={`grid ${s} place-items-center rounded-full disabled:opacity-30`}
        aria-label={t('product.decrease')}
      >
        <Minus size={16} />
      </button>
      <span className="min-w-6 text-center font-semibold tabular-nums" aria-live="polite">{value}</span>
      <button
        type="button"
        onClick={() => onChange(Math.min(max, value + 1))}
        disabled={value >= max}
        className={`grid ${s} place-items-center rounded-full disabled:opacity-30`}
        aria-label={t('product.increase')}
      >
        <Plus size={16} />
      </button>
    </div>
  )
}
