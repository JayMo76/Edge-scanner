import { create } from 'zustand'
import type { Alert, ConnectionStatus, FeedId, HodLodEvent } from '../types'
import { openAlertSocket, type AlertSocket } from '../lib/ws'
import { api } from '../lib/api'

// ONE WebSocket for the whole app: the scanner's unified feed on the page's own
// port (7777 live, 7787 demo; the Vite dev server on 5174 talks to 7777). Every
// alert carries `source` (system | custom); windows filter client-side.
const host = window.location.hostname
const pagePort = Number(window.location.port)
const basePort = pagePort >= 7000 ? pagePort : Number(import.meta.env.VITE_SCANNER_PORT || 7777)
export const FEED_URL = `ws://${host}:${basePort}/ws/alerts?sources=all`
export const SOURCES: FeedId[] = ['system', 'custom']
export const SOURCE_LABEL: Record<FeedId, string> = { system: 'System setups', custom: 'Custom setups' }
export const SOURCE_SHORT: Record<FeedId, string> = { system: 'SYS', custom: 'CS' }
/** Sources worth showing as chips, counts and filter options. 'system' exists
 *  only when the backend reports the system_setups capability. */
export const visibleSources = (hasSystem: boolean): FeedId[] => (hasSystem ? SOURCES : ['custom'])
/** kept for older imports */
export const FEED_LABEL = SOURCE_LABEL
const MAX_ALERTS = 8000
const MAX_EVENTS = 500

export function alertKey(a: Alert): string {
  return `${a.symbol}:${a.timestamp}:${a.setup ?? a.trigger}`
}

/** Normalized source. Older archives carry "rr" (the former name of the system
 *  feed) or no `source` at all; both map onto 'system' | 'custom'. */
export function sourceOf(a: Alert | { source?: string; custom?: boolean }): FeedId {
  const s = (a as { source?: string }).source
  if (s === 'custom' || a.custom) return 'custom'
  if (s === 'system' || s === 'rr') return 'system'
  return 'system'
}

/** Alerts from retired producers (any other `source` in an old archive) are dropped. */
function isRetired(a: Alert): boolean {
  const s = (a as { source?: string }).source
  return s != null && s !== 'system' && s !== 'custom' && s !== 'rr'
}

interface FeedsState {
  alerts: Alert[]                          // newest first, every source
  status: ConnectionStatus
  lastSeq: number
  latest: Alert | null
  counts: Record<FeedId, number>
  events: HodLodEvent[]
  eventsSeq: number
  connectAll(): void
  disconnectAll(): void
  acquireEvents(): () => void
  /** dev helper: inject a fake alert (sound/TTS testing) */
  fakeAlert(source: FeedId, partial?: Partial<Alert>): void
}

let socket: AlertSocket | null = null
const keys = new Set<string>()
let eventsRef = 0
let eventsTimer: ReturnType<typeof setInterval> | null = null

const countBySource = (alerts: Alert[]): Record<FeedId, number> => {
  const c: Record<FeedId, number> = { system: 0, custom: 0 }
  for (const a of alerts) c[sourceOf(a)] += 1
  return c
}

export const useFeeds = create<FeedsState>()((set, get) => ({
  alerts: [],
  status: 'disconnected',
  lastSeq: 0,
  latest: null,
  counts: { system: 0, custom: 0 },
  events: [],
  eventsSeq: 0,

  connectAll() {
    if (socket) return
    socket = openAlertSocket(FEED_URL, {
      onStatus: st => set({ status: st }),
      onReplay: alerts => {
        const tagged = alerts.filter(a => !isRetired(a)).map(a => ({ ...a, source: sourceOf(a) }))
        keys.clear()
        for (const a of tagged) keys.add(alertKey(a))
        set({ alerts: tagged.slice(0, MAX_ALERTS), counts: countBySource(tagged) })
      },
      onAlert: raw => {
        if (isRetired(raw)) return
        const a = { ...raw, source: sourceOf(raw) }
        const k = alertKey(a)
        if (keys.has(k)) return
        keys.add(k)
        set(s => {
          const next = [a, ...s.alerts]
          if (next.length > MAX_ALERTS) {
            for (const old of next.splice(MAX_ALERTS)) keys.delete(alertKey(old))
          }
          return { alerts: next, lastSeq: s.lastSeq + 1, latest: a, counts: { ...s.counts, [a.source]: s.counts[a.source] + 1 } }
        })
      },
    })
  },

  disconnectAll() {
    socket?.close()
    socket = null
  },

  acquireEvents() {
    eventsRef += 1
    if (!eventsTimer) {
      const tick = async () => {
        try {
          const since = get().eventsSeq
          const d = await api.events(since, 200)
          if (d.events.length || d.seq !== since) {
            set(s => ({
              events: [...d.events.slice().reverse(), ...s.events].slice(0, MAX_EVENTS),
              eventsSeq: d.seq,
            }))
          }
        } catch { /* endpoint may not exist on an older scanner; keep polling quietly */ }
      }
      void tick()
      eventsTimer = setInterval(tick, 2000)
    }
    return () => {
      eventsRef = Math.max(0, eventsRef - 1)
      if (eventsRef === 0 && eventsTimer) { clearInterval(eventsTimer); eventsTimer = null }
    }
  },

  fakeAlert(source, partial = {}) {
    const now = new Date().toISOString()
    const a: Alert = {
      symbol: 'TEST', direction: 'long', timestamp: now, price: 100 + Math.random(),
      trigger: 'hod:high', triggers_fired: [], score: 70,
      market_regime: 'neutral', conditions: {}, vwap: null, ema3: null, ema9: null, source,
      ...(source === 'system' ? { setup: 'SYS_TEST', setup_label: 'Test system setup', suggested_stop: 99.5, stop_pct: 0.5, stop_ok: true, context: { rvol: 1.8, gap_pct: 1.2 } } : {}),
      ...(source === 'custom' ? { setup: 'cs_test', setup_label: 'Test setup', custom: true, entry_trigger: 'hod:high', trigger_note: 'new high of day' } : {}),
      ...partial,
    }
    keys.add(alertKey(a))
    set(s => ({ alerts: [a, ...s.alerts], lastSeq: s.lastSeq + 1, latest: a, counts: { ...s.counts, [source]: s.counts[source] + 1 } }))
  },
}))

declare global {
  interface Window { __scannerDebug?: { fakeAlert: FeedsState['fakeAlert'] } }
}
window.__scannerDebug = { fakeAlert: (f, p) => useFeeds.getState().fakeAlert(f, p) }
