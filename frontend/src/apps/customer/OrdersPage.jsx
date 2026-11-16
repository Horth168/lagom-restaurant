import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Receipt } from 'lucide-react'
import { useI18n } from '../../i18n'
import { api } from '../../lib/api'
import { formatUSD } from '../../lib/money'
import { useCustomer } from './CustomerContext'
import { Header } from './Header'

const STATUS_KEY = {
  PENDING_PAYMENT: 'pay.waiting', PAID: 'track.step.PAID', PREPARING: 'track.step.PREPARING',
  READY: 'track.step.READY', SERVED: 'track.step.SERVED', CANCELLED: 'track.cancelled', EXPIRED: 'pay.expired',
}

/** All orders placed from this phone at this table (this table session only). */
export function OrdersPage() {
  const { t, pick } = useI18n()
  const { headers } = useCustomer()
  const [orders, setOrders] = useState(null)

  useEffect(() => {
    api('/api/public/orders', { headers }).then(setOrders).catch(() => setOrders([]))
  }, [headers])

  return (
    <div className="min-h-dvh pb-12">
      <Header title={t('orders.title')} backTo=".." />
      <main className="mx-auto max-w-2xl px-4">
        {orders === null ? (
          <div className="space-y-3 pt-4">{[0, 1].map((i) => <div key={i} className="skeleton h-20 rounded-xl" />)}</div>
        ) : orders.length === 0 ? (
          <div className="flex flex-col items-center gap-4 pt-24 text-center">
            <Receipt size={40} strokeWidth={1.25} className="text-sand" />
            <p className="text-muted">{t('orders.empty')}</p>
            <Link to=".." className="rounded-full bg-brand px-6 py-3 text-sm font-medium text-on-brand">{t('cart.browse')}</Link>
          </div>
        ) : (
          <ul className="divide-y divide-line">
            {orders.map((o) => (
              <li key={o.public_id}>
                <Link to={`../order/${o.public_id}`} className="flex items-center gap-4 py-4">
                  <span className="font-display text-2xl text-accent">#{o.number}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{o.items.map((i) => `${i.quantity}× ${pick(i.name)}`).join(', ')}</span>
                    <span className="block text-xs text-muted">{t(STATUS_KEY[o.status] ?? 'orders.view')}</span>
                  </span>
                  <span className="text-sm font-semibold tabular-nums">{formatUSD(o.total_usd_cents)}</span>
                  <ChevronRight size={18} className="text-muted" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
