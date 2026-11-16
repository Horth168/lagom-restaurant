// Money helpers. Amounts arrive from the API as integers (USD cents, whole riel).

export function formatUSD(cents) {
  const sign = cents < 0 ? '-' : ''
  const abs = Math.abs(cents)
  return `${sign}$${Math.floor(abs / 100).toLocaleString('en-US')}.${String(abs % 100).padStart(2, '0')}`
}

export function formatKHR(riel) {
  return `${Math.round(riel).toLocaleString('en-US')}៛`
}

// Same rule as the backend: convert, then round to the nearest 100 riel (half up)
export function usdCentsToKhr(cents, khrPerUsd) {
  const riel = (cents * Number(khrPerUsd)) / 100
  return Math.floor(riel / 100 + 0.5) * 100
}

/** Returns { primary, secondary } strings following the owner's display settings. */
export function formatPrice(cents, settings) {
  const rate = settings?.khr_per_usd ?? 4100
  const usd = formatUSD(cents)
  const khr = formatKHR(usdCentsToKhr(cents, rate))
  const khrFirst = settings?.display_currency === 'KHR'
  const showSecondary = settings?.show_secondary_currency ?? true
  return {
    primary: khrFirst ? khr : usd,
    secondary: showSecondary ? (khrFirst ? usd : khr) : null,
  }
}
