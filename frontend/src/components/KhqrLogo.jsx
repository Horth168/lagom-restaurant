// KHQR logo (Cambodia's national QR payment standard), redrawn as SVG from the official
// artwork so it stays sharp at any size. Coordinates follow the official 1248 × 514 badge.
const RED = '#E1232E'

function Letters({ fill }) {
  return (
    <g fill={fill}>
      {/* K */}
      <rect x="95" y="125" width="46" height="263" />
      <polygon points="141,242 253,125 307,125 187,251 314,388 258,388 141,266" />
      {/* H */}
      <rect x="348" y="125" width="45" height="263" />
      <rect x="521" y="125" width="46" height="263" />
      <rect x="393" y="235" width="128" height="38" />
      {/* Q: rounded frame open at the bottom right (the tail), with a small square inside */}
      <path d="M648 125 H821 A40 40 0 0 1 861 165 V356 L821 316 V190 A25 25 0 0 0 796 165 H673 A25 25 0 0 0 648 190 V319 A25 25 0 0 0 673 344 H795 L835 384 H648 A40 40 0 0 1 608 344 V165 A40 40 0 0 1 648 125 Z" />
      <rect x="688" y="208" width="92" height="95" rx="10" />
      {/* R: arch with a left leg and a diagonal leg */}
      <path d="M900 250 A124 124 0 0 1 1148 250 V254 H1108 V250 A84 84 0 0 0 940 250 V384 A40 40 0 0 1 900 344 Z" />
      <polygon points="1012,297 1066,297 1152,388 1096,388" />
    </g>
  )
}

/** The KHQR word only (no background). `color` is the letter colour. */
export function KhqrLogo({ height = 20, color = RED, className = '', title = 'KHQR', ...rest }) {
  return (
    <svg viewBox="95 125 1057 263" height={height} className={className} role="img" aria-label={title} {...rest}>
      <Letters fill={color} />
    </svg>
  )
}

/** The official red KHQR badge: white letters on a red rounded rectangle. */
export function KhqrBadge({ height = 24, className = '', title = 'KHQR', ...rest }) {
  return (
    <svg viewBox="0 0 1248 514" height={height} className={className} role="img" aria-label={title} {...rest}>
      <rect width="1248" height="514" rx="76" fill={RED} />
      <Letters fill="#ffffff" />
    </svg>
  )
}
