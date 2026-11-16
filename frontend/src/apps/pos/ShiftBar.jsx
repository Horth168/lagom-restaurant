/* Cash drawer shift: open with the starting cash, close by counting the drawer.
 * LAGOM shows what should be in the drawer and the difference. */
import { useCallback, useEffect, useState } from 'react'
import { Calculator, Lock, Unlock } from 'lucide-react'
import { Sheet } from '../../components/Sheet'
import { Button, Field, inputCls, parseUsd, useToast } from '../../components/ui'
import { appLocale, useI18n } from '../../i18n'
import { formatKHR, formatUSD } from '../../lib/money'
import { useStaff } from '../../lib/staffAuth'

const riel = (text) => {
  const n = Number(String(text ?? '').replace(/[,\s៛]/g, '') || 0)
  return Number.isInteger(n) && n >= 0 ? n : null
}

export function ShiftBar() {
  const { t } = useI18n()
  const { staffApi, can } = useStaff()
  const toast = useToast()
  const [shift, setShift] = useState(undefined) // undefined = loading, null = closed
  const [dialog, setDialog] = useState(null) // 'open' | 'close' | 'result'
  const [usd, setUsd] = useState('')
  const [khr, setKhr] = useState('')
  const [note, setNote] = useState('')
  const [result, setResult] = useState(null)
  const allowed = can('payments.cash')

  const load = useCallback(() => {
    if (allowed) staffApi('/api/pos/shift').then(setShift).catch(() => setShift(null))
  }, [allowed, staffApi])
  useEffect(() => { load() }, [load])

  if (!allowed || shift === undefined) return null

  function start(kind) {
    setUsd('')
    setKhr('')
    setNote('')
    if (kind === 'close') load() // fresh expected amounts
    setDialog(kind)
  }

  async function submit() {
    const cents = parseUsd(usd || '0')
    const r = riel(khr)
    if (cents === null || r === null) return toast(t('shift.badAmount'), 'bad')
    try {
      if (dialog === 'open') {
        setShift(await staffApi('/api/pos/shift/open', { method: 'POST', body: { opening_usd_cents: cents, opening_khr: r } }))
        setDialog(null)
        toast(t('shift.opened'))
      } else {
        const out = await staffApi('/api/pos/shift/close', { method: 'POST', body: { counted_usd_cents: cents, counted_khr: r, note } })
        setResult(out)
        setShift(null)
        setDialog('result')
      }
    } catch (e) {
      toast(e.message, 'bad')
    }
  }

  const since = shift ? new Date(shift.opened_at).toLocaleTimeString(appLocale(), { hour: '2-digit', minute: '2-digit' }) : ''
  return (
    <>
      {shift ? (
        <Button variant="ghost" onClick={() => start('close')} title={t('shift.closeTitle')}>
          <Lock size={16} /> <span className="hidden lg:inline">{t('shift.openSince', { time: since })}</span>
        </Button>
      ) : (
        <Button variant="secondary" onClick={() => start('open')} className="border-series-2 text-series-2">
          <Unlock size={16} /> <span className="hidden sm:inline">{t('shift.open')}</span>
        </Button>
      )}

      <Sheet open={dialog === 'open' || dialog === 'close'} onClose={() => setDialog(null)} label={t(dialog === 'open' ? 'shift.open' : 'shift.closeTitle')}>
        <div className="space-y-4 p-6">
          <h2 className="font-display text-2xl">{t(dialog === 'open' ? 'shift.open' : 'shift.closeTitle')}</h2>
          <p className="text-sm text-muted">{t(dialog === 'open' ? 'shift.openHint' : 'shift.closeHint')}</p>
          {dialog === 'close' && shift && (
            <div className="rounded-lg bg-surface-2 p-3 text-sm">
              {t('shift.cashOrders', { n: shift.cash_orders })} · ABA KHQR {formatUSD(shift.khqr_usd_cents)}
            </div>
          )}
          <Field label={t(dialog === 'open' ? 'shift.startUsd' : 'shift.countedUsd')}>
            <input className={inputCls} inputMode="decimal" placeholder="0.00" value={usd} onChange={(e) => setUsd(e.target.value)} autoFocus />
          </Field>
          <Field label={t(dialog === 'open' ? 'shift.startKhr' : 'shift.countedKhr')}>
            <input className={inputCls} inputMode="numeric" placeholder="0" value={khr} onChange={(e) => setKhr(e.target.value)} />
          </Field>
          {dialog === 'close' && (
            <Field label={t('shift.note')}>
              <input className={inputCls} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
            </Field>
          )}
          <Button variant="primary" size="lg" className="w-full" onClick={submit}>
            {t(dialog === 'open' ? 'shift.openBtn' : 'shift.closeBtn')}
          </Button>
        </div>
      </Sheet>

      <Sheet open={dialog === 'result'} onClose={() => setDialog(null)} label={t('shift.result')}>
        {result && <ShiftResult shift={result} onDone={() => setDialog(null)} />}
      </Sheet>
    </>
  )
}

export function ShiftResult({ shift, onDone }) {
  const { t } = useI18n()
  const du = shift.difference_usd_cents
  const dk = shift.difference_khr
  const ok = du === 0 && dk === 0
  return (
    <div className="space-y-4 p-6">
      <h2 className="flex items-center gap-2 font-display text-2xl"><Calculator size={22} /> {t('shift.result')}</h2>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-line">
          <tr><td className="py-2 text-muted">{t('shift.expected')}</td><td className="py-2 text-right font-semibold tabular-nums">{formatUSD(shift.expected_usd_cents)}{shift.expected_khr ? ` + ${formatKHR(shift.expected_khr)}` : ''}</td></tr>
          <tr><td className="py-2 text-muted">{t('shift.counted')}</td><td className="py-2 text-right font-semibold tabular-nums">{formatUSD(shift.counted_usd_cents)}{shift.counted_khr ? ` + ${formatKHR(shift.counted_khr)}` : ''}</td></tr>
          <tr>
            <td className="py-2 text-muted">{t('shift.difference')}</td>
            <td className={`py-2 text-right text-lg font-bold tabular-nums ${ok ? 'text-series-1' : 'text-danger'}`}>
              {ok ? t('shift.matches') : `${du >= 0 ? '+' : '−'}${formatUSD(Math.abs(du))}${dk ? ` · ${dk > 0 ? '+' : '−'}${formatKHR(Math.abs(dk))}` : ''}`}
            </td>
          </tr>
        </tbody>
      </table>
      {!ok && <p className="text-sm text-muted">{t('shift.diffHint')}</p>}
      {onDone && <Button variant="primary" size="lg" className="w-full" onClick={onDone}>{t('common.close')}</Button>}
    </div>
  )
}
