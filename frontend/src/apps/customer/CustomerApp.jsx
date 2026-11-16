import { Route, Routes, useParams } from 'react-router-dom'
import { Mark } from '../../components/Logo'
import { useI18n } from '../../i18n'
import { CustomerProvider, useCustomer } from './CustomerContext'
import { MenuPage } from './MenuPage'
import { CartPage } from './CartPage'
import { OrderPage } from './OrderPage'
import { OrdersPage } from './OrdersPage'

export default function CustomerApp() {
  const { qrToken } = useParams()
  return (
    <CustomerProvider qrToken={qrToken}>
      <Gate />
    </CustomerProvider>
  )
}

function Gate() {
  const { session, menu, error, retry } = useCustomer()
  const { t } = useI18n()

  if (error) {
    return (
      <Centered>
        <Mark size={56} className="text-brand" />
        <p className="max-w-xs text-center text-ink">{t(error === 'invalid' ? 'entry.invalid' : 'entry.offline')}</p>
        {error === 'offline' && (
          <button onClick={retry} className="rounded-full bg-brand px-6 py-3 text-sm font-medium text-on-brand">
            {t('common.retry')}
          </button>
        )}
      </Centered>
    )
  }
  if (!session || !menu) return <MenuSkeleton />

  return (
    <Routes>
      <Route index element={<MenuPage />} />
      <Route path="cart" element={<CartPage />} />
      <Route path="orders" element={<OrdersPage />} />
      <Route path="order/:publicId" element={<OrderPage />} />
    </Routes>
  )
}

function Centered({ children }) {
  return <div className="min-h-dvh flex flex-col items-center justify-center gap-6 px-6">{children}</div>
}

function MenuSkeleton() {
  const { t } = useI18n()
  return (
    <div className="mx-auto max-w-2xl px-4 pt-4" aria-busy="true" aria-label={t('entry.opening')}>
      <div className="flex items-center justify-between">
        <div className="skeleton h-7 w-32 rounded" />
        <div className="skeleton h-8 w-24 rounded-full" />
      </div>
      <div className="skeleton mt-5 h-11 w-full rounded-xl" />
      <div className="skeleton mt-5 h-36 w-full rounded-2xl" />
      <div className="mt-6 flex gap-2">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-9 w-24 rounded-full" />)}
      </div>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="mt-6 flex gap-4">
          <div className="skeleton size-24 rounded-xl" />
          <div className="flex-1 space-y-2 pt-1">
            <div className="skeleton h-4 w-2/3 rounded" />
            <div className="skeleton h-3 w-full rounded" />
            <div className="skeleton h-3 w-1/3 rounded" />
          </div>
        </div>
      ))}
    </div>
  )
}
