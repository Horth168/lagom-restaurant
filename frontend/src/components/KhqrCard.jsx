/* KHQR payment card in the official style: red header with the KHQR mark and cut corner,
 * merchant, amount, dashed line, QR with the currency badge. Used on phones and on the POS screen.
 */
import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { KhqrLogo } from './KhqrLogo'
import { useI18n } from '../i18n'

export function KhqrCard({ qrString, amountMinor, currency, merchant = 'LAGOM', onQr, size = 300 }) {
  const { t } = useI18n()
  const [qrSrc, setQrSrc] = useState('')

  useEffect(() => {
    // High error correction so the currency badge in the middle never stops the QR from scanning
    QRCode.toDataURL(qrString, { errorCorrectionLevel: 'H', margin: 0, width: 640, color: { dark: '#000000', light: '#ffffff' } })
      .then((src) => {
        setQrSrc(src)
        onQr?.(src)
      })
      .catch(() => setQrSrc(''))
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onQr is a notification only
  }, [qrString])

  const isKhr = currency === 'KHR'
  const amountText = isKhr ? Math.round(amountMinor).toLocaleString('en-US') : (amountMinor / 100).toFixed(2)

  return (
    <div className="w-full overflow-hidden rounded-[18px] bg-white text-[#1a1a1a] shadow-[0_10px_40px_rgba(0,0,0,0.14)]" style={{ maxWidth: size }}>
      <div className="relative h-[52px] bg-[#E1232E]">
        <div className="flex h-full items-center justify-center pr-6">
          <KhqrLogo height={20} color="#ffffff" />
        </div>
        <span className="absolute right-0 bottom-0 h-0 w-0 border-b-[22px] border-l-[22px] border-b-white border-l-transparent" aria-hidden="true" />
      </div>
      <div className="px-7 pt-4">
        <div className="text-[13px] font-medium text-[#555]">{merchant}</div>
        <div className="mt-0.5 flex items-baseline gap-1.5">
          <span className="text-[26px] font-bold leading-none tabular-nums">{amountText}</span>
          <span className="text-[13px] font-semibold text-[#555]">{isKhr ? 'KHR' : 'USD'}</span>
        </div>
      </div>
      <div className="mx-7 my-4 border-t-2 border-dashed border-[#d9d9d9]" aria-hidden="true" />
      <div className="relative px-7 pb-7">
        {qrSrc ? <img src={qrSrc} alt={t('pay.qrAlt')} className="aspect-square w-full" /> : <div className="skeleton aspect-square w-full rounded" />}
        {qrSrc && (
          <span className="absolute top-1/2 left-1/2 grid size-11 -translate-x-1/2 -translate-y-[calc(50%+14px)] place-items-center rounded-full border-[3px] border-white bg-black text-[19px] font-bold text-white">
            {isKhr ? '៛' : '$'}
          </span>
        )}
      </div>
    </div>
  )
}
