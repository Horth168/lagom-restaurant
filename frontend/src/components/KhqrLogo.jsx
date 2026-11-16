// KHQR wordmark (Cambodia's national QR payment standard), redrawn as SVG so it stays sharp.
// Shown on the payment card so customers recognise a standard KHQR they can pay with any bank app.
export function KhqrLogo({ height = 20, color = '#E1232E', className = '', title = 'KHQR' }) {
  return (
    <svg viewBox="0 0 735 175" height={height} className={className} role="img" aria-label={title}>
      <g fill={color}>
        <rect x="0" y="0" width="35" height="175" />
        <polygon points="35,82 117,0 166,0 35,131" />
        <polygon points="62,106 86,82 178,175 129,175" />
        <rect x="182" y="0" width="35" height="175" />
        <rect x="287" y="0" width="35" height="175" />
        <rect x="217" y="72" width="70" height="32" />
        <path
          fillRule="evenodd"
          d="M397 0 H475 A45 45 0 0 1 520 45 V128 L473 175 H397 A45 45 0 0 1 352 130 V45 A45 45 0 0 1 397 0 Z M402 34 A14 14 0 0 0 388 48 V127 A14 14 0 0 0 402 141 H460 L487 114 V48 A14 14 0 0 0 473 34 Z"
        />
        <path d="M419 52 H467 A8 8 0 0 1 475 60 V108 L460 123 H419 A8 8 0 0 1 411 115 V60 A8 8 0 0 1 419 52 Z" />
        <polygon points="455,117 478,94 536,154 536,175 515,175" />
        <path d="M562 175 V85 A85 85 0 0 1 732 85 V96 H697 V85 A50 50 0 0 0 597 85 V175 Z" />
        <polygon points="628,123 652,99 735,175 686,175" />
      </g>
    </svg>
  )
}
