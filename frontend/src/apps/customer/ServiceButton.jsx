/* Customer at a table: "Call a waiter" / "Request the bill". Staff see it live on the POS and admin. */
import { useCallback, useEffect, useState } from 'react'
import { BellRing, CheckCircle2, ReceiptText } from 'lucide-react'
import { Sheet } from '../../components/Sheet'
import { useI18n } from '../../i18n'
import { api } from '../../lib/api'
import { useLiveChannel } from '../../lib/realtime'
import { useCustomer } from './CustomerContext'

export function ServiceButton() {
  const { t } = useI18n()
  const { session, headers } = useCustomer()
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState([]) // kinds waiting for staff
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const atTable = session && !session.pickup

  const load = useCallback(() => {
    if (atTable) api('/api/public/service-requests', { headers }).then((rs) => setPending(rs.map((r) => r.kind))).catch(() => {})
  }, [atTable, headers])
  useEffect(() => { load() }, [load])
  useLiveChannel('/api/ws/customer', { session: session?.session_token }, (msg) => {
    if (msg.type === 'service_done' || msg.type === 'reconnected') load()
  }, !!atTable)

  if (!atTable) return null

  async function ask(kind) {
    setBusy(true)
    setError('')
    try {
      await api('/api/public/service-requests', { method: 'POST', headers, body: { kind } })
      setPending((p) => [...new Set([...p, kind])])
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const choice = (kind, Icon) => {
    const waiting = pending.includes(kind)
    return (
      <button onClick={() => ask(kind)} disabled={busy || waiting}
        className={`flex w-full items-center gap-4 rounded-2xl border p-4 text-left transition ${waiting ? 'border-series-1 bg-series-1/10' : 'border-line bg-surface hover:bg-surface-2'}`}>
        {waiting ? <CheckCircle2 size={26} className="text-series-1" /> : <Icon size={26} className="text-accent" />}
        <span>
          <span className="block font-medium">{t(kind === 'bill' ? 'service.askBill' : 'service.askWaiter')}</span>
          <span className="block text-sm text-muted">{waiting ? t('service.coming') : t(kind === 'bill' ? 'service.billHint' : 'service.waiterHint')}</span>
        </span>
      </button>
    )
  }

  return (
    <>
      <button onClick={() => setOpen(true)} aria-label={t('service.title')}
        className="relative grid size-9 place-items-center rounded-full text-ink hover:bg-surface-2">
        <BellRing size={19} strokeWidth={1.75} />
        {pending.length > 0 && <span className="absolute top-1.5 right-1.5 size-2 rounded-full bg-series-1" />}
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} label={t('service.title')}>
        <div className="space-y-3 p-6">
          <h2 className="font-display text-2xl">{t('service.title')}</h2>
          {choice('waiter', BellRing)}
          {choice('bill', ReceiptText)}
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        </div>
      </Sheet>
    </>
  )
}
