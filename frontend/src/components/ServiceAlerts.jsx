/* Staff strip: tables that pressed "Call waiter" or "Request the bill". Live, with a chime. */
import { useCallback, useEffect, useState } from 'react'
import { BellRing, Check, ReceiptText } from 'lucide-react'
import { useI18n } from '../i18n'
import { useLiveChannel } from '../lib/realtime'
import { useStaff } from '../lib/staffAuth'
import { chime } from '../apps/kds/sound'

export function ServiceAlerts({ className = '' }) {
  const { t } = useI18n()
  const { staffApi, token, can } = useStaff()
  const allowed = can('orders.view')
  const [items, setItems] = useState([])

  const load = useCallback(() => {
    if (allowed) staffApi('/api/admin/service-requests').then(setItems).catch(() => {})
  }, [allowed, staffApi])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000) // safety net if the live connection drops
    return () => clearInterval(id)
  }, [load])

  useLiveChannel('/api/ws/staff', { token, station: null }, (msg) => {
    if (msg.type === 'service') chime()
    if (['service', 'service_done', 'reconnected'].includes(msg.type)) load()
  }, allowed)

  async function done(id) {
    setItems((xs) => xs.filter((x) => x.id !== id))
    await staffApi(`/api/admin/service-requests/${id}/done`, { method: 'POST' }).catch(load)
  }

  if (!items.length) return null
  return (
    <div role="status" className={`flex flex-wrap gap-2 ${className}`}>
      {items.map((r) => (
        <div key={r.id} className="flex items-center gap-2 rounded-full bg-series-2/15 py-1.5 pr-1.5 pl-3 text-sm font-medium text-ink">
          {r.kind === 'bill' ? <ReceiptText size={16} className="text-series-2" /> : <BellRing size={16} className="text-series-2" />}
          <span><b>{r.table}</b> · {t(r.kind === 'bill' ? 'service.bill' : 'service.waiter')}</span>
          <button onClick={() => done(r.id)} className="flex items-center gap-1 rounded-full bg-surface px-2.5 py-1 text-xs font-semibold hover:bg-surface-2">
            <Check size={13} /> {t('service.done')}
          </button>
        </div>
      ))}
    </div>
  )
}
