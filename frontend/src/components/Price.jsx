import { formatPrice } from '../lib/money'

/** Shows a price in the owner's display currency, with the other currency underneath. */
export function Price({ cents, settings, className = '', secondaryClassName = '', inline = false }) {
  const { primary, secondary } = formatPrice(cents, settings)
  if (inline) {
    return (
      <span className={className}>
        {primary}
        {secondary && <span className={`ml-1.5 text-muted font-normal ${secondaryClassName}`}>{secondary}</span>}
      </span>
    )
  }
  return (
    <span className={`inline-flex flex-col leading-tight ${className}`}>
      <span className="tabular-nums">{primary}</span>
      {secondary && <span className={`text-xs text-muted font-normal tabular-nums ${secondaryClassName}`}>{secondary}</span>}
    </span>
  )
}
