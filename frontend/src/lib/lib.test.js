import { describe, expect, it } from 'vitest'
import { formatKHR, formatPrice, formatUSD, usdCentsToKhr } from './money'
import { addLine, defaultSelection, lineKey, missingGroups, previewUnitPrice, setQuantity, toggleOption } from './cartMath'
import { translate } from '../i18n/index.jsx'
import en from '../i18n/en.json'
import km from '../i18n/km.json'
import zh from '../i18n/zh.json'

const latte = {
  id: 1,
  price_usd_cents: 275,
  option_groups: [
    { id: 10, selection: 'SINGLE', min_select: 1, max_select: 1,
      options: [{ id: 100, price_delta_usd_cents: 0, is_default: false, is_available: true },
                { id: 101, price_delta_usd_cents: 50, is_default: true, is_available: true }] },
    { id: 11, selection: 'MULTIPLE', min_select: 0, max_select: 2,
      options: [{ id: 110, price_delta_usd_cents: 50, is_default: false, is_available: true },
                { id: 111, price_delta_usd_cents: 30, is_default: false, is_available: true },
                { id: 112, price_delta_usd_cents: 50, is_default: false, is_available: true }] },
  ],
}

describe('money', () => {
  it('formats USD and KHR', () => {
    expect(formatUSD(275)).toBe('$2.75')
    expect(formatUSD(123456)).toBe('$1,234.56')
    expect(formatKHR(11300)).toBe('11,300៛')
  })
  it('rounds KHR like the backend (nearest 100, half up)', () => {
    expect(usdCentsToKhr(275, '4100')).toBe(11300)
    expect(usdCentsToKhr(750, '4100')).toBe(30800)
    expect(usdCentsToKhr(100, '4100')).toBe(4100)
  })
  it('respects display currency', () => {
    expect(formatPrice(100, { khr_per_usd: '4100', display_currency: 'KHR', show_secondary_currency: true }))
      .toEqual({ primary: '4,100៛', secondary: '$1.00' })
    expect(formatPrice(100, { khr_per_usd: '4100', display_currency: 'USD', show_secondary_currency: false }))
      .toEqual({ primary: '$1.00', secondary: null })
  })
})

describe('cart math', () => {
  it('preselects defaults and previews price', () => {
    const sel = defaultSelection(latte)
    expect(sel).toEqual({ 10: [101], 11: [] })
    expect(previewUnitPrice(latte, sel)).toBe(325)
  })
  it('enforces single choice and max selections', () => {
    let sel = defaultSelection(latte)
    sel = toggleOption(latte.option_groups[0], sel, 100)
    expect(sel[10]).toEqual([100])
    sel = toggleOption(latte.option_groups[1], sel, 110)
    sel = toggleOption(latte.option_groups[1], sel, 111)
    sel = toggleOption(latte.option_groups[1], sel, 112) // over the max of 2: ignored
    expect(sel[11]).toEqual([110, 111])
    sel = toggleOption(latte.option_groups[1], sel, 110)
    expect(sel[11]).toEqual([111])
  })
  it('reports missing required groups', () => {
    expect(missingGroups(latte, { 10: [], 11: [] }).map((g) => g.id)).toEqual([10])
  })
  it('merges identical lines and removes at zero', () => {
    let lines = addLine([], { product_id: 1, option_ids: [101, 110], special_instructions: '', quantity: 1 })
    lines = addLine(lines, { product_id: 1, option_ids: [110, 101], special_instructions: ' ', quantity: 2 })
    expect(lines).toHaveLength(1)
    expect(lines[0].quantity).toBe(3)
    expect(lines[0].key).toBe(lineKey(1, [101, 110]))
    expect(setQuantity(lines, lines[0].key, 0)).toHaveLength(0)
  })
})

describe('translations', () => {
  it('every language has every key', () => {
    const keys = Object.keys(en).sort()
    expect(Object.keys(km).sort()).toEqual(keys)
    expect(Object.keys(zh).sort()).toEqual(keys)
  })
  it('fills variables', () => {
    expect(translate('en', 'cart.items', { n: 3 })).toBe('3 items')
  })
})
