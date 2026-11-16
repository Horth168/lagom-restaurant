/* KHQR payment card drawn like the official KHQR card that bank apps show:
 * red header with the KHQR mark and a flap hanging down on the right, merchant name,
 * amount, a dashed line across the card, and the QR with the red KHQR emblem in the middle.
 * The same drawing is shown on screen and saved as the "Save QR image" picture.
 * Used on customers' phones and on the POS screen.
 */
import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { KhqrLogo } from './KhqrLogo'
import { useI18n } from '../i18n'

const RED = '#CC0000'
const W = 300
const H = 440
const QR = { x: 30, y: 170, size: 240 }
const FONT = 'Inter, "Noto Sans Khmer", Arial, sans-serif'

/** 8-point star outline of the KHQR emblem, centred on (cx, cy). */
function starPoints(cx, cy, outer, inner) {
  const pts = []
  for (let i = 0; i < 16; i++) {
    const r = i % 2 ? inner : outer
    const a = (Math.PI / 8) * i - Math.PI / 2
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`)
  }
  return pts.join(' ')
}

/** Turns the on-screen card into a PNG (2× sharper) for saving to the phone's photos. */
function svgToPng(svg) {
  const xml = new XMLSerializer().serializeToString(svg)
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = W * 2
      canvas.height = H * 2
      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0, W * 2, H * 2)
      resolve(canvas.toDataURL('image/png'))
    }
    img.onerror = reject
    img.src = url
  })
}

export function KhqrCard({ qrString, amountMinor, currency, merchant = 'LAGOM', onQr, size = 300 }) {
  const { t } = useI18n()
  const [qrSrc, setQrSrc] = useState('')
  const svgRef = useRef(null)

  useEffect(() => {
    // High error correction so the emblem in the middle never stops the QR from scanning
    QRCode.toDataURL(qrString, { errorCorrectionLevel: 'H', margin: 0, width: 640, color: { dark: '#000000', light: '#ffffff' } })
      .then(setQrSrc)
      .catch(() => setQrSrc(''))
  }, [qrString])

  useEffect(() => {
    if (!qrSrc || !onQr || !svgRef.current) return
    svgToPng(svgRef.current).then(onQr).catch(() => onQr(qrSrc)) // fall back to the plain QR
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onQr is a notification only
  }, [qrSrc, merchant, amountMinor, currency])

  const isKhr = currency === 'KHR'
  const amountText = isKhr ? Math.round(amountMinor).toLocaleString('en-US') : (amountMinor / 100).toFixed(2)
  const cx = QR.x + QR.size / 2
  const cy = QR.y + QR.size / 2

  return (
    <div className="w-full overflow-hidden rounded-[14px] bg-white shadow-[0_10px_40px_rgba(0,0,0,0.14)]" style={{ maxWidth: size }}>
      <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full"
        role="img" aria-label={`KHQR · ${merchant} · ${amountText} ${isKhr ? 'KHR' : 'USD'}`}>
        <rect width={W} height={H} rx="14" fill="#ffffff" />
        {/* Red header with the flap hanging down on the right */}
        <path d={`M0 14 Q0 0 14 0 H${W - 14} Q${W} 0 ${W} 14 V88 L${W - 30} 60 H0 Z`} fill={RED} />
        <KhqrLogo x={(W - 84) / 2} y={20} width={84} height={20} color="#ffffff" />

        <text x="30" y="98" fontFamily={FONT} fontSize="16" fill="#222222">{merchant}</text>
        <text x="30" y="133" fontFamily={FONT} fill="#111111">
          <tspan fontSize="22" fontWeight="700">{amountText}</tspan>
          <tspan dx="6" fontSize="11" fill="#333333">{isKhr ? 'KHR' : 'USD'}</tspan>
        </text>
        <line x1="0" y1="152" x2={W} y2="152" stroke="#9a9a9a" strokeWidth="1" strokeDasharray="4 3" />

        {qrSrc ? (
          <>
            <image href={qrSrc} x={QR.x} y={QR.y} width={QR.size} height={QR.size} />
            {/* KHQR emblem: red circle, white ring, 8-point star and the "C" mark */}
            <circle cx={cx} cy={cy} r="21" fill={RED} stroke="#ffffff" strokeWidth="4" />
            <polygon points={starPoints(cx, cy, 14, 10.5)} fill="none" stroke="#ffffff" strokeWidth="1.8" strokeLinejoin="round" />
            <path d={`M${cx + 4.5} ${cy - 5.5} H${cx - 3} A2.5 2.5 0 0 0 ${cx - 5.5} ${cy - 3} V${cy + 3} A2.5 2.5 0 0 0 ${cx - 3} ${cy + 5.5} H${cx + 4.5}`}
              fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" />
          </>
        ) : (
          <rect x={QR.x} y={QR.y} width={QR.size} height={QR.size} rx="6" fill="#eeeeee" />
        )}
      </svg>
      <span className="sr-only">{t('pay.qrAlt')}</span>
    </div>
  )
}
