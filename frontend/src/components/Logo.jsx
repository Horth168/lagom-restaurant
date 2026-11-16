// LAGOM logo as React components. Shapes match brand/build_brand.py.
// The ring/wordmark use `currentColor`, so they adapt to light and dark mode.
import { useId } from 'react'

const LETTERS = [
  ['M0 0V40H24', 24],
  ['M0 40L15 0L30 40M5.6 26H24.4', 30],
  ['M34.14 5.86A20 20 0 1 0 40 20H22', 40],
  ['M20 0A20 20 0 1 1 20 40A20 20 0 1 1 20 0Z', 40],
  ['M0 40V0L17 26L34 0V40', 34],
]
const TRACKING = 14

export function Mark({ size = 32, className = '', title = 'LAGOM' }) {
  const id = useId()
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className} role="img" aria-label={title}>
      <defs>
        <clipPath id={id}>
          <circle cx="32" cy="32" r="20" />
        </clipPath>
      </defs>
      <circle cx="32" cy="32" r="26" fill="none" stroke="currentColor" strokeWidth="4" />
      <rect x="6" y="36" width="52" height="26" fill="#C58B50" clipPath={`url(#${id})`} />
    </svg>
  )
}

export function Wordmark({ height = 16, className = '' }) {
  const offsets = LETTERS.map((_, i) => LETTERS.slice(0, i).reduce((sum, [, w]) => sum + w + TRACKING, 0))
  const paths = LETTERS.map(([d], i) => <path key={d} transform={`translate(${offsets[i]} 0)`} d={d} />)
  const width = offsets.at(-1) + LETTERS.at(-1)[1]
  return (
    <svg viewBox={`-2 -2 ${width + 4} 44`} height={height} className={className} role="img" aria-label="LAGOM">
      <g fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="square">
        {paths}
      </g>
    </svg>
  )
}

export function LogoHorizontal({ height = 28, className = '' }) {
  return (
    <span className={`inline-flex items-center ${className}`} style={{ gap: height * 0.45 }}>
      <Mark size={height} title="" />
      <Wordmark height={height * 0.5} />
    </span>
  )
}
