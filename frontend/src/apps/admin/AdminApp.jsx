import { ThemeIcon } from '../../components/ThemeIcon'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import {
  Boxes, ChefHat, Globe, Landmark, LayoutDashboard, LogOut, Percent, QrCode, Receipt, Settings, ShoppingBag,
  ScrollText, Star, Users, UtensilsCrossed, Wallet, X,
} from 'lucide-react'
import { LogoHorizontal } from '../../components/Logo'
import { ServiceAlerts } from '../../components/ServiceAlerts'
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
const StaffPage = lazy(() => import('./StaffPage'))
const AuditLog = lazy(() => import('./AuditLog'))
const MyAccount = lazy(() => import('./MyAccount'))
const Deals = lazy(() => import('./Deals'))
const Reviews = lazy(() => import('./Reviews'))

const NAV = [
  { to: 'overview', label: 'admin.nav.overview', icon: LayoutDashboard, perm: 'dashboard.view', el: <Overview /> },
  { to: 'orders', label: 'admin.nav.orders', icon: Receipt, perm: 'orders.view', el: <Orders /> },
  { to: 'payments', label: 'admin.nav.payments', icon: Wallet, perm: 'payments.view', el: <Payments /> },
  { to: 'menu', label: 'admin.nav.menu', icon: UtensilsCrossed, perm: 'menu.view', el: <MenuAdmin /> },
  { to: 'deals', label: 'admin.nav.deals', icon: Percent, perm: 'menu.view', el: <Deals /> },
  { to: 'reviews', label: 'admin.nav.reviews', icon: Star, perm: 'dashboard.view', el: <Reviews /> },
  { to: 'inventory', label: 'admin.nav.inventory', icon: Boxes, perm: 'inventory.view', el: <Inventory /> },
  { to: 'finance', label: 'admin.nav.finance', icon: Landmark, perm: 'finance.view', el: <Finance /> },
  { to: 'tables', label: 'admin.nav.tables', icon: QrCode, perm: 'tables.manage', el: <Tables /> },
  { to: 'staff', label: 'admin.nav.staff', icon: Users, perm: 'staff.manage', el: <StaffPage /> },
  { to: 'audit', label: 'admin.nav.audit', icon: ScrollText, perm: 'audit.view', el: <AuditLog /> },
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
            <Route index element={<Navigate to={`/admin/${allowed[0].to}`} replace />} />
            {allowed.map((n) => <Route key={n.to} path={`${n.to}/*`} element={n.el} />)}
            <Route path="*" element={<Navigate to={`/admin/${allowed[0].to}`} replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </ToastProvider>
  )
}

function Shell({ items, children }) {
  const { t, lang } = useI18n()
  const { user, can, logout, saveLanguage } = useStaff()
  const [account, setAccount] = useState(false)
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState(currentTheme)
  const nextLang = LANGUAGES[(LANGUAGES.findIndex((l) => l.code === lang) + 1) % LANGUAGES.length]
  const switchTheme = (e) => setTheme(toggleTheme(e))
  const { pathname } = useLocation()

  const navItem = (active) =>
    `press flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] transition-colors duration-150 ${
      active ? 'bg-nav-active font-semibold text-cream' : 'text-cream/75 hover:bg-nav-hover hover:text-cream'
    }`

  const sidebar = (
    <nav className="flex h-full flex-col bg-nav text-cream transition-colors duration-300">
      <div className="flex h-16 shrink-0 items-center justify-between px-5">
        <LogoHorizontal height={26} className="text-cream" />
        <button className="press -mr-2 grid size-10 place-items-center rounded-full hover:bg-nav-hover lg:hidden" onClick={() => setOpen(false)} aria-label={t('common.close')}>
          <X size={20} />
        </button>
      </div>
      <ul className="no-scrollbar flex-1 space-y-0.5 overflow-y-auto overscroll-contain px-3 py-2">
        {items.map((n) => (
          <li key={n.to}>
            <NavLink to={`/admin/${n.to}`} onClick={() => setOpen(false)} className={({ isActive }) => navItem(isActive)}>
              <n.icon size={18} strokeWidth={1.75} /> {t(n.label)}
            </NavLink>
          </li>
        ))}
        <li className="px-3 pt-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-cream/45">{t('admin.nav.screens')}</li>
        {can('orders.create') && (
          <li><Link to="/pos" className={navItem(false)}><ShoppingBag size={18} strokeWidth={1.75} /> POS</Link></li>
        )}
        {['kitchen', 'drinks', 'dessert'].some((s) => can(`kds.${s}`)) && (
          <li><Link to="/kds" className={navItem(false)}><ChefHat size={18} strokeWidth={1.75} /> {t('kds.title')}</Link></li>
        )}
      </ul>
      <div className="shrink-0 border-t border-cream/10 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <button onClick={() => setAccount(true)} className="press mb-1 block w-full rounded-xl px-3 py-2 text-left text-sm transition-colors hover:bg-nav-hover" title={t('acct.title')}>
          <div className="font-medium">{user?.full_name}</div>
          <div className="text-xs text-cream/60">{t(`role.${user?.role}`)} · {t('acct.title')}</div>
        </button>
        <div className="flex gap-1">
          <button onClick={() => saveLanguage(nextLang.code)} className="press flex flex-1 items-center justify-center gap-1.5 rounded-xl py-2 text-sm text-cream/80 transition-colors hover:bg-nav-hover" title={t('lang.title')}>
            <Globe size={16} /> {nextLang.label}
          </button>
          <button onClick={switchTheme} className="press grid size-10 place-items-center rounded-xl text-cream/80 transition-colors hover:bg-nav-hover" aria-label={t('theme.toggle')}>
            <ThemeIcon theme={theme} size={17} />
          </button>
          <button onClick={logout} className="press grid size-10 place-items-center rounded-xl text-cream/80 transition-colors hover:bg-nav-hover" aria-label={t('kds.signOut')}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </nav>
  )

  return (
    <div className="min-h-dvh bg-bg lg:pl-60">
      {account && <Suspense fallback={null}><MyAccount onClose={() => setAccount(false)} /></Suspense>}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 lg:block">{sidebar}</aside>
      <MobileDrawer open={open} onClose={() => setOpen(false)} closeLabel={t('common.close')}>{sidebar}</MobileDrawer>
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-bg/85 px-3 backdrop-blur-md transition-colors duration-300 lg:hidden">
        <button onClick={() => setOpen(true)} aria-label={t('admin.menu')} aria-expanded={open}
          className="press grid size-11 place-items-center rounded-full text-ink hover:bg-surface-2">
          <Burger open={open} />
        </button>
        <LogoHorizontal height={22} className="text-brand" />
        <div className="ml-auto flex items-center">
          <button onClick={() => saveLanguage(nextLang.code)} className="press flex h-10 items-center gap-1.5 rounded-full px-3 text-sm text-ink hover:bg-surface-2" title={t('lang.title')}>
            <Globe size={17} strokeWidth={1.75} /> <span className="text-[13px]">{nextLang.label}</span>
          </button>
          <button onClick={switchTheme} className="press grid size-10 place-items-center rounded-full text-ink hover:bg-surface-2" aria-label={t('theme.toggle')}>
            <ThemeIcon theme={theme} size={19} />
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 pt-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] sm:p-6 lg:p-8">
        <ServiceAlerts className="mb-4" />
        {/* a soft fade-in whenever you open another page */}
        <div key={pathname.split('/')[2] || ''} className="animate-page-in">{children}</div>
      </main>
    </div>
  )
}

/**
 * Phone menu that behaves like iPhone's own drawers: glides in on the iOS curve, the page
 * dims behind it, and it follows your finger when you swipe it closed (a short flick is enough).
 * Escape and tapping outside also close it; the page behind cannot scroll while it is open.
 */
function MobileDrawer({ open, onClose, closeLabel, children }) {
  const panel = useRef(null)
  const shade = useRef(null)
  const drag = useRef(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    const before = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = before
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  function down(e) {
    if (e.pointerType === 'mouse') return
    drag.current = { x: e.clientX, y: e.clientY, t: performance.now(), dx: 0, moving: false }
  }
  function move(e) {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (!d.moving) {
      if (Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) { drag.current = null; return } // scrolling the list
      if (Math.abs(dx) < 8) return
      d.moving = true
      panel.current.style.transition = 'none'
      shade.current.style.transition = 'none'
    }
    d.dx = Math.min(0, dx)
    const w = panel.current.offsetWidth
    panel.current.style.transform = `translate3d(${d.dx}px,0,0)`
    shade.current.style.opacity = String(Math.max(0, 1 + d.dx / w))
  }
  function up() {
    const d = drag.current
    drag.current = null
    if (!d?.moving) return
    const el = panel.current
    const speed = d.dx / Math.max(1, performance.now() - d.t) // px per ms (negative = towards the left)
    el.style.transition = ''
    shade.current.style.transition = ''
    shade.current.style.opacity = ''
    // close after dragging a third of the way, or a quick flick of at least 50 px
    if (d.dx < -el.offsetWidth * 0.33 || (speed < -0.5 && d.dx < -50)) {
      el.style.transform = 'translate3d(-100%,0,0)'
      onClose()
    } else {
      el.style.transform = 'translate3d(0,0,0)'
    }
  }

  return (
    <div className={`fixed inset-0 z-50 lg:hidden ${open ? '' : 'pointer-events-none'}`} aria-hidden={!open}>
      <button
        ref={shade}
        tabIndex={open ? 0 : -1}
        onClick={onClose}
        aria-label={closeLabel}
        className="absolute inset-0 bg-black/50 motion-reduce:transition-none"
        style={{ opacity: open ? 1 : 0, transition: 'opacity 380ms var(--ease-ios)' }}
      />
      <aside
        ref={panel}
        inert={!open}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        className="relative h-full w-[280px] max-w-[85vw] shadow-[8px_0_40px_rgba(0,0,0,0.35)] will-change-transform motion-reduce:transition-none"
        style={{
          transform: open ? 'translate3d(0,0,0)' : 'translate3d(-100%,0,0)',
          transition: 'transform 440ms var(--ease-ios)',
          touchAction: 'pan-y',
        }}
      >
        {children}
      </aside>
    </div>
  )
}

/** Three lines that glide into an X (transform only, so it stays smooth on phones). */
function Burger({ open }) {
  const line = 'absolute left-0 top-[7px] block h-[2px] w-[22px] rounded-full bg-current transition-[transform,translate,rotate,scale,opacity] duration-[440ms] ease-ios motion-reduce:transition-none'
  return (
    <span className="relative block h-4 w-[22px]" aria-hidden="true">
      <span className={`${line} ${open ? 'rotate-45' : '-translate-y-[7px]'}`} />
      <span className={`${line} ${open ? 'scale-x-0 opacity-0' : 'opacity-100'}`} />
      <span className={`${line} ${open ? '-rotate-45' : 'translate-y-[7px]'}`} />
    </span>
  )
}

export function PageTitle({ title, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="font-display text-[28px] leading-tight sm:text-3xl">{title}</h1>
      <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}
