// Pure cart helpers (no React), so they are easy to test.
// NOTE: prices calculated here are only a preview while the user chooses options.
// The cart screen always shows the server's quote, and the server decides the final price.

export function lineKey(productId, optionIds, instructions = '') {
  return `${productId}:${[...optionIds].sort((a, b) => a - b).join(',')}:${instructions.trim()}`
}

export function defaultSelection(product) {
  const sel = {}
  for (const g of product.option_groups) {
    const defaults = g.options.filter((o) => o.is_default && o.is_available).map((o) => o.id)
    sel[g.id] = g.selection === 'SINGLE' ? defaults.slice(0, 1) : defaults.slice(0, g.max_select)
  }
  return sel
}

export function toggleOption(group, selected, optionId) {
  const current = selected[group.id] || []
  if (group.selection === 'SINGLE') return { ...selected, [group.id]: [optionId] }
  if (current.includes(optionId)) return { ...selected, [group.id]: current.filter((id) => id !== optionId) }
  if (current.length >= group.max_select) return selected
  return { ...selected, [group.id]: [...current, optionId] }
}

export function missingGroups(product, selected) {
  return product.option_groups.filter((g) => (selected[g.id] || []).length < g.min_select)
}

/** Price after a timed deal (percent off), rounded like the server (half to even). Preview only. */
export function dealPrice(cents, percent) {
  if (!percent) return cents
  const exact = (cents * (100 - percent)) / 100
  const floor = Math.floor(exact)
  const diff = exact - floor
  if (Math.abs(diff - 0.5) < 1e-9) return floor % 2 === 0 ? floor : floor + 1
  return Math.round(exact)
}

export function previewUnitPrice(product, selected) {
  let cents = product.price_usd_cents
  for (const g of product.option_groups) {
    for (const o of g.options) if ((selected[g.id] || []).includes(o.id)) cents += o.price_delta_usd_cents
  }
  return dealPrice(cents, product.deal?.percent)
}

export function selectedOptionIds(product, selected) {
  return product.option_groups.flatMap((g) => selected[g.id] || [])
}

export function addLine(lines, line) {
  const key = lineKey(line.product_id, line.option_ids, line.special_instructions)
  const existing = lines.find((l) => l.key === key)
  if (existing) {
    return lines.map((l) => (l.key === key ? { ...l, quantity: Math.min(50, l.quantity + line.quantity) } : l))
  }
  return [...lines, { ...line, key }]
}

export function setQuantity(lines, key, quantity) {
  if (quantity <= 0) return lines.filter((l) => l.key !== key)
  return lines.map((l) => (l.key === key ? { ...l, quantity: Math.min(50, quantity) } : l))
}

export function itemCount(lines) {
  return lines.reduce((n, l) => n + l.quantity, 0)
}
