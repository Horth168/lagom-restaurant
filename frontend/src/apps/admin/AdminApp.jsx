import { lazy, Suspense, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import {
  Boxes, ChefHat, Globe, Landmark, LayoutDashboard, LogOut, Menu as MenuIcon, Moon, QrCode, Receipt, Settings, ShoppingBag,
  Sun, UtensilsCrossed, Wallet, X,
} from 'lucide-react'
import { LogoHorizontal } from '../../components/Logo'
import { ToastProvider } from '../../components/ui'
import { LANGUAGES, useI18n } from '../../i18n'
import { useStaff } from '../../lib/staffAuth'
import { currentTheme, toggleTheme } from '../../lib/theme'

const Overview = lazy(() => import('./Overview'))
const Orders = lazy(() => import('./Orders'))
const Payments = lazy(() => import('./Payments'))
const MenuAdmin = lazy(() => import('./MenuAdmin'))
const Tables = lazy(() => import('./Tables'))
const SettingsPage = lazy(() => import('./SettingsPage'))
const Inventory = lazy(() => import('./Inventory'))
const Finance = lazy(() => import('./Finance'))

const NAV = [
  { to: 'overview', label: 'admin.nav.overview', icon: LayoutDashboard, perm: 'dashboard.view', el: <Overview /> },
  { to: 'orders', label: 'admin.nav.orders', icon: Receipt, perm: 'orders.view', el: <Orders /> },
  { to: 'payments', label: 'admin.nav.payments', icon: Wallet, perm: 'payments.view', el: <Payments /> },
  { to: 'menu', label: 'admin.nav.menu', icon: UtensilsCrossed, perm: 'menu.view', el: <MenuAdmin /> },
  { to: 'inventory', label: 'admin.nav.inventory', icon: Boxes, perm: 'inventory.view', el: <Inventory /> },
  { to: 'finance', label: 'admin.nav.finance', icon: Landmark, perm: 'finance.view', el: <Finance /> },
  { to: 'tables', label: 'admin.nav.tables', icon: QrCode, perm: 'tables.manage', el: <Tables /> },
  { to: 'settings', label: 'admin.nav.settings', icon: Settings, perm: 'settings.edit', el: <SettingsPage /> },
]

export default function AdminApp() {
  const { t } = useI18n()
  const { can } = useStaff()
  const allowed = NAV.filter((n) => can(n.perm))
  if (!allowed.length) {
    // Staff without admin pages go to the screen made for them
    if (can('orders.create')) return <Navigate to="/pos" replace />
    if (['kitchen', 'drinks', 'dessert'].some((s) => can(`kds.${s}`))) return <Navigate to="/kds" replace />
    return <p className="p-10 text-center text-muted">{t('admin.noAccess')}</p>
  }
  return (
    <ToastProvider>
      <Shell items={allowed}>
        <Suspense fallback={<div className="p-8"><div className="skeleton h-40 rounded-xl" /></div>}>
          <Routes>
            <Route index element={<Navigate to={allowed[0].to} replace />} />
            {allowed.map((n) => <Route key={n.to} path={`${n.to}/*`} element={n.el} />)}
            <Route path="*" element={<Navigate to={allowed[0].to} replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </ToastProvider>
  )
}

function Shell({ items, children }) {
  const { t, lang, setLang } = useI18n()
  const { user, can, logout } = useStaff()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState(currentTheme)
  const nextLang = LANGUAGES[(LANGUAGES.findIndex((l) => l.code === lang) + 1) % LANGUAGES.length]

  const sidebar = (
    <nav className="flex h-full flex-col bg-forest text-cream">
      <div className="flex h-16 items-center justify-between px-5">
        <LogoHorizontal height={26} className="text-cream" />
        <button className="lg:hidden" onClick={() => setOpen(false)} aria-label={t('common.close')}><X size={20} /></button>
      </div>
      <ul className="flex-1 space-y-0.5 px-3 py-2">
        {items.map((n) => (
          <li key={n.to}>
            <NavLink
              to={`/admin/${n.to}`}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] ${isActive ? 'bg-cream/15 font-semibold text-cream' : 'text-cream/75 hover:bg-cream/10'}`
              }
            >
              <n.icon size={18} strokeWidth={1.75} /> {t(n.label)}
            </NavLink>
          </li>
        ))}
        <li className="pt-4 text-[11px] font-semibold uppercase tracking-wider text-cream/45 px-3">{t('admin.nav.screens')}</li>
        {can('orders.create') && (
          <li><Link to="/pos" className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] text-cream/75 hover:bg-cream/10"><ShoppingBag size={18} strokeWidth={1.75} /> POS</Link></li>
        )}
        {['kitchen', 'drinks', 'dessert'].some((s) => can(`kds.${s}`)) && (
          <li><Link to="/kds" className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] text-cream/75 hover:bg-cream/10"><ChefHat size={18} strokeWidth={1.75} /> {t('kds.title')}</Link></li>
        )}
      </ul>
      <div className="border-t border-cream/10 p-3">
        <div className="px-3 pb-2 text-sm">
          <div className="font-medium">{user?.full_name}</div>
          <div className="text-xs text-cream/60">{user?.role}</div>
        </div>
        <div className="flex gap-1">
          <button onClick={() => setLang(nextLang.code)} className="flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 text-sm text-cream/80 hover:bg-cream/10" title={t('lang.title')}>
            <Globe size={16} /> {nextLang.label}
          </button>
          <button onClick={() => setTheme(toggleTheme())} className="grid size-9 place-items-center rounded-lg text-cream/80 hover:bg-cream/10" aria-label={t('theme.toggle')}>
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button onClick={logout} className="grid size-9 place-items-center rounded-lg text-cream/80 hover:bg-cream/10" aria-label={t('kds.signOut')}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </nav>
  )

  return (
    <div className="min-h-dvh bg-bg lg:pl-60">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} aria-label={t('common.close')} />
          <aside className="relative h-full w-64 animate-fade-in">{sidebar}</aside>
        </div>
      )}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-bg/90 px-4 backdrop-blur lg:hidden">
        <button onClick={() => setOpen(true)} aria-label={t('admin.menu')}><MenuIcon size={22} /></button>
        <LogoHorizontal height={22} className="text-brand" />
      </header>
      <main className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">{children}</main>
    </div>
  )
}

export function PageTitle({ title, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="font-display text-3xl">{title}</h1>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}
