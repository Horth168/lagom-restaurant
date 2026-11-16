/* Kitchen Display System: one screen per station (Kitchen, Drinks, Dessert).
 * Paid orders appear instantly (WebSocket), oldest first, with a waiting timer and big buttons for tablets.
 */
import { KitchenTicket } from '../../components/KitchenTicket'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { Bell, BellOff, Check, Flag, LogOut, Maximize, Minimize, Printer, StickyNote } from 'lucide-react'
import { Mark } from '../../components/Logo'
import { appLocale, useI18n } from '../../i18n'
import { useLiveChannel } from '../../lib/realtime'
import { useStaff } from '../../lib/staffAuth'
import { chime } from './sound'

const STATIONS = ['KITCHEN', 'DRINKS', 'DESSERT']
const NEXT_ACTION = { new: 'accept', accepted: 'start', preparing: 'ready', ready: 'served' }
const POLL_MS = 15000

export default function KdsApp() {
  return (
    <Routes>
      <Route index element={<StationPicker />} />
      <Route path=":station" element={<StationScreen />} />
    </Routes>
  )
}

function allowedStations(can) {
  return STATIONS.filter((s) => can(`kds.${s.toLowerCase()}`))
}

function StationPicker() {
  const { t } = useI18n()
  const { can, logout } = useStaff()
  const stations = allowedStations(can)
  if (stations.length === 1) return <Navigate to={stations[0].toLowerCase()} replace />
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-8 bg-[#101612] px-6 text-cream">
      <Mark size={56} className="text-cream" />
      <h1 className="font-display text-3xl">{stations.length ? t('kds.choose') : t('kds.noAccess')}</h1>
      <div className="flex flex-wrap justify-center gap-4">
        {stations.map((s) => (
          <Link key={s} to={s.toLowerCase()} className="grid h-32 w-48 place-items-center rounded-2xl bg-[#1d2822] text-2xl font-semibold hover:bg-[#26342c]">
            {t(`kds.station.${s}`)}
          </Link>
        ))}
      </div>
      <button onClick={logout} className="text-sm text-cream/60 underline">{t('kds.signOut')}</button>
    </main>
  )
}

function StationScreen() {
  const { station: slug } = useParams()
  const station = slug?.toUpperCase()
  const { t } = useI18n()
  const { can, token, staffApi, logout, user } = useStaff()
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(null)
  const [muted, setMuted] = useState(() => localStorage.getItem('lagom.kds.muted') === '1')
  const [soundReady, setSoundReady] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const known = useRef(null)
  // Kitchen ticket printer: print a ticket for every new order (this device only)
  const [autoPrint, setAutoPrint] = useState(() => localStorage.getItem('lagom.kds.autoprint') === '1')
  const autoPrintRef = useRef(autoPrint)
  const [printQueue, setPrintQueue] = useState([])

  const load = useCallback(async () => {
    try {
      const d = await staffApi(`/api/kds/${station}`)
      // Chime when a ticket appears that this screen has not seen yet
      const ids = new Set(d.active.map((x) => x.public_id))
      const fresh = known.current ? d.active.filter((x) => !known.current.has(x.public_id)) : []
      if (fresh.length && !muted) chime()
      if (fresh.length && autoPrintRef.current) setPrintQueue((q) => [...q, ...fresh])
      known.current = ids
      setData(d)
    } catch {
      /* keep showing the last data; the connection badge shows the problem */
    }
  }, [station, staffApi, muted])

  const live = useLiveChannel('/api/ws/staff', { token, station }, () => load(), !!token && STATIONS.includes(station))

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS) // safety net if a live message is missed
    return () => clearInterval(id)
  }, [load])

  // Print queued tickets one by one (the browser shows its print dialog unless kiosk printing is on)
  useEffect(() => {
    if (!printQueue.length) return
    const id = setTimeout(() => {
      window.print()
      setPrintQueue((q) => q.slice(1))
    }, 200)
    return () => clearTimeout(id)
  }, [printQueue])

  useEffect(() => {
    const onFs = () => setFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', onFs)
    return () => document.removeEventListener('fullscreenchange', onFs)
  }, [])

  if (!STATIONS.includes(station)) return <Navigate to="/kds" replace />
  if (!can(`kds.${slug}`)) return <Navigate to="/kds" replace />

  async function act(publicId, action) {
    setBusy(publicId + action)
    try {
      await staffApi(`/api/kds/${station}/orders/${publicId}/${action}`, { method: 'POST' })
      await load()
    } finally {
      setBusy(null)
    }
  }

  async function toggleItem(item) {
    const status = item.status === 'READY' ? 'PREPARING' : 'READY'
    await staffApi(`/api/kds/items/${item.id}/status`, { method: 'POST', body: { status } })
    await load()
  }

  function toggleAutoPrint() {
    const next = !autoPrint
    setAutoPrint(next)
    autoPrintRef.current = next
    localStorage.setItem('lagom.kds.autoprint', next ? '1' : '0')
  }

  function toggleMute() {
    const next = !muted
    setMuted(next)
    localStorage.setItem('lagom.kds.muted', next ? '1' : '0')
    if (!next) chime()
  }

  const stations = allowedStations(can)
  const active = data?.active ?? []

  return (
    <div className="min-h-dvh bg-[#101612] text-cream" onClick={() => !soundReady && setSoundReady(true)}>
      {/* Phone: logo + station tabs (slide sideways) on one row, tools on a second row.
          Tablet/TV: everything on one row. Nothing is ever wider than the screen. */}
      <header className="sticky top-0 z-20 border-b border-white/10 bg-[#101612]/95 px-3 pt-[env(safe-area-inset-top)] backdrop-blur sm:px-4">
        <div className="flex min-h-14 flex-wrap items-center gap-x-3 gap-y-1 py-2 sm:min-h-16">
          <div className="flex min-w-0 basis-full items-center gap-3 sm:flex-1 sm:basis-auto">
            <Mark size={28} className="shrink-0 text-cream" title="LAGOM" />
            <nav className="no-scrollbar flex min-w-0 gap-1.5 overflow-x-auto">
              {stations.map((s) => (
                <Link
                  key={s}
                  to={`/kds/${s.toLowerCase()}`}
                  className={`press shrink-0 whitespace-nowrap rounded-full px-4 py-2 text-[15px] font-semibold ${s === station ? 'bg-cream text-forest' : 'text-cream/70 hover:bg-white/10'}`}
                >
                  {t(`kds.station.${s}`)}
                </Link>
              ))}
            </nav>
            <span className="hidden shrink-0 text-sm whitespace-nowrap text-cream/60 tabular-nums lg:inline">{t('kds.active', { n: active.length })}</span>
          </div>
          <div className="flex w-full shrink-0 items-center gap-0.5 sm:ml-auto sm:w-auto sm:gap-1">
            <span
              title={live === 'live' ? t('kds.live') : t('kds.offline')}
              className={`mr-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold sm:mr-1 ${live === 'live' ? 'bg-olive/30 text-[#c9d6a8]' : 'bg-[#E1232E]/25 text-[#ffb3b3]'}`}
            >
              <span className={`size-2 rounded-full ${live === 'live' ? 'bg-[#a8c27a]' : 'animate-pulse bg-[#ff6b6b]'}`} />
              {live === 'live' ? t('kds.live') : t('kds.offline')}
              <span className="text-cream/50 sm:hidden">· {t('kds.active', { n: active.length })}</span>
            </span>
            <Clock />
            <IconButton label={autoPrint ? t('kds.autoPrintOff') : t('kds.autoPrintOn')} onClick={toggleAutoPrint}>
              <Printer size={20} className={autoPrint ? 'text-gold' : ''} />
            </IconButton>
            <IconButton label={muted ? t('kds.unmute') : t('kds.mute')} onClick={toggleMute}>
              {muted ? <BellOff size={20} /> : <Bell size={20} />}
            </IconButton>
            {document.fullscreenEnabled && (
              <IconButton
                label={t('kds.fullscreen')}
                onClick={() => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen?.())}
              >
                {fullscreen ? <Minimize size={20} /> : <Maximize size={20} />}
              </IconButton>
            )}
            <IconButton label={`${t('kds.signOut')} (${user?.full_name ?? ''})`} onClick={logout}>
              <LogOut size={20} />
            </IconButton>
          </div>
        </div>
      </header>

      {!muted && !soundReady && (
        <button onClick={() => { setSoundReady(true); chime() }} className="block w-full bg-gold/90 py-2 text-center text-sm font-semibold text-forest">
          {t('kds.enableSound')}
        </button>
      )}

      <main className="p-3 pb-[max(1rem,env(safe-area-inset-bottom))] sm:p-4">
        {data && active.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-32 text-center text-cream/60">
            <Mark size={56} className="text-cream/40" />
            <p className="text-xl">{t('kds.empty')}</p>
            <p className="text-sm">{t('kds.emptyHint')}</p>
          </div>
        ) : (
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr))]">
            {active.map((o) => (
              <Ticket key={o.public_id} order={o} serverTime={data.server_time} busy={busy} onAct={act} onToggleItem={toggleItem}
                onPrint={() => setPrintQueue((q) => [...q, o])} />
            ))}
          </div>
        )}

        {data?.done?.length > 0 && (
          <section className="mt-10">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-cream/50">{t('kds.done')}</h2>
            <div className="flex flex-wrap gap-2">
              {[...data.done].reverse().map((o) => (
                <span key={o.public_id} className="rounded-lg bg-white/5 px-3 py-2 text-sm text-cream/60">
                  #{o.number} · {o.table || t('kds.takeaway')}
                </span>
              ))}
            </div>
          </section>
        )}
      </main>
      <KitchenTicket order={printQueue[0]} station={t(`kds.station.${station}`)} />
    </div>
  )
}

function IconButton({ label, onClick, children }) {
  return (
    <button onClick={onClick} aria-label={label} title={label} className="press grid size-10 place-items-center rounded-full text-cream/80 hover:bg-white/10 sm:size-11">
      {children}
    </button>
  )
}

function Clock() {
  const now = useNow(15000)
  return <span className="mr-1 text-lg font-semibold tabular-nums text-cream/80">{now.toLocaleTimeString(appLocale(), { hour: '2-digit', minute: '2-digit' })}</span>
}

function useNow(ms = 1000) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), ms)
    return () => clearInterval(id)
  }, [ms])
  return now
}

const STAGE_STYLE = {
  new: 'border-gold bg-[#2a2416]',
  accepted: 'border-sand/60 bg-[#1d2822]',
  preparing: 'border-[#6f8fb0] bg-[#1b2530]',
  ready: 'border-[#8fae5a] bg-[#1f2a18]',
}

function Ticket({ order: o, busy, onAct, onToggleItem, onPrint }) {
  const { t, lang } = useI18n()
  const now = useNow(1000)
  const waitedMs = Math.max(0, now - new Date(o.paid_at))
  const waitedMin = Math.floor(waitedMs / 60000)
  const target = Math.max(...o.items.map((i) => i.prep_minutes), 5)
  const timerColor = o.stage === 'ready' ? 'text-[#a8c27a]' : waitedMin >= target * 2 ? 'text-[#ff7a7a]' : waitedMin >= target ? 'text-gold' : 'text-cream/80'
  const next = NEXT_ACTION[o.stage]
  const itemName = (i) => (lang === 'km' && i.name_km) || (lang === 'zh' && i.name_zh) || i.name
  const others = Object.entries(o.other_stations)
    .map(([s, n]) => `${n} ${t(`kds.station.${s}`)}`)
    .join(' · ')

  return (
    <article className={`flex flex-col overflow-hidden rounded-2xl border-2 ${STAGE_STYLE[o.stage]} ${o.stage === 'new' ? 'shadow-[0_0_0_3px_rgba(197,139,80,0.25)]' : ''}`}>
      <header className="flex items-start justify-between gap-2 px-4 pt-3">
        <div>
          <div className="font-display text-4xl leading-none">#{o.number}</div>
          <div className="mt-1 flex items-center gap-2 text-[15px] font-semibold text-cream/80">
            {o.table || t('kds.takeaway')}
            <button onClick={onPrint} aria-label={t('kds.printTicket')} title={t('kds.printTicket')}
              className="grid size-8 place-items-center rounded-full text-cream/60 hover:bg-white/10">
              <Printer size={16} />
            </button>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold tabular-nums ${timerColor}`}>
            {waitedMin}:{String(Math.floor((waitedMs % 60000) / 1000)).padStart(2, '0')}
          </div>
          <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-cream/60">{t(`kds.stage.${o.stage}`)}</div>
        </div>
      </header>

      <ul className="mt-3 flex-1 space-y-1 px-2">
        {o.items.map((i) => {
          const ready = i.status === 'READY' || i.status === 'SERVED'
          return (
            <li key={i.id}>
              <button
                onClick={() => o.stage !== 'new' && onToggleItem(i)}
                disabled={o.stage === 'new'}
                className={`flex w-full items-start gap-3 rounded-xl px-2 py-2 text-left ${ready ? 'opacity-50' : 'hover:bg-white/5'}`}
                title={t('kds.tapItem')}
              >
                <span className={`mt-0.5 grid size-7 shrink-0 place-items-center rounded-md border-2 ${ready ? 'border-[#8fae5a] bg-[#8fae5a] text-[#101612]' : 'border-cream/30'}`}>
                  {ready && <Check size={16} strokeWidth={3} />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className={`block text-[19px] font-semibold leading-snug ${ready ? 'line-through' : ''}`}>
                    <span className="text-gold">{i.quantity}×</span> {itemName(i)}
                  </span>
                  {i.options.length > 0 && <span className="block text-[15px] text-cream/70">{i.options.join(' · ')}</span>}
                  {i.special_instructions && (
                    <span className="mt-1 flex items-start gap-1.5 rounded-md bg-gold/20 px-2 py-1 text-[15px] font-semibold text-[#f3c58f]">
                      <Flag size={15} className="mt-0.5 shrink-0" /> {i.special_instructions}
                    </span>
                  )}
                </span>
              </button>
            </li>
          )
        })}
      </ul>

      {o.customer_note && (
        <p className="mx-4 mt-2 flex gap-2 rounded-lg bg-white/5 p-2 text-[15px] text-cream/85">
          <StickyNote size={16} className="mt-0.5 shrink-0 text-gold" /> {o.customer_note}
        </p>
      )}
      {others && <p className="mx-4 mt-2 text-sm text-cream/55">{t('kds.also', { list: others })}</p>}

      <footer className="mt-3 flex gap-2 p-3 pt-0">
        {o.stage === 'ready' && (
          <button
            onClick={() => onAct(o.public_id, 'recall')}
            disabled={!!busy}
            className="h-14 rounded-xl bg-white/10 px-4 text-[15px] font-semibold text-cream/80 disabled:opacity-50"
          >
            {t('kds.action.recall')}
          </button>
        )}
        {next && (
          <button
            onClick={() => onAct(o.public_id, next)}
            disabled={!!busy}
            className={`h-14 flex-1 rounded-xl text-[17px] font-bold disabled:opacity-50 ${
              o.stage === 'preparing' ? 'bg-[#8fae5a] text-[#101612]' : o.stage === 'ready' ? 'bg-cream text-forest' : 'bg-gold text-[#101612]'
            }`}
          >
            {busy === o.public_id + next ? '…' : t(`kds.action.${next}`)}
          </button>
        )}
      </footer>
    </article>
  )
}
