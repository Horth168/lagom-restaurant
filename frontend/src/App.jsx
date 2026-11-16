import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { I18nProvider, useI18n } from './i18n'
import { Mark, Wordmark } from './components/Logo'

// Each section is loaded only when needed, so customers' phones download only the customer app
const CustomerApp = lazy(() => import('./apps/customer/CustomerApp'))

export default function App() {
  return (
    <I18nProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="min-h-dvh" />}>
          <Routes>
            <Route path="/t/:qrToken/*" element={<CustomerApp />} />
            <Route path="*" element={<Welcome />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </I18nProvider>
  )
}

function Welcome() {
  const { t } = useI18n()
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-7 px-6 text-center">
      <Mark size={72} className="text-brand" />
      <div className="flex flex-col items-center gap-3 text-brand">
        <Wordmark height={30} />
        <span className="text-[11px] uppercase tracking-[0.3em] text-accent">{t('brand.descriptor')}</span>
      </div>
      <p className="max-w-sm text-muted">{t('home.body')}</p>
      <span className="text-[11px] font-semibold uppercase tracking-[0.3em] text-gold">{t('brand.slogan')}</span>
    </main>
  )
}
