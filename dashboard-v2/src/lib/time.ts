// All timestamps from the scanner are ET ISO strings (or UTC ISO). Everything
// the user sees is ET. lightweight-charts only knows UTC, so chart times are
// shifted so its "UTC" reads as ET wall-clock (toSecET).

const ET = 'America/New_York'

const partsFmt = new Intl.DateTimeFormat('en-US', {
  timeZone: ET, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
})

function etParts(d: Date): Record<string, number> {
  const out: Record<string, number> = {}
  for (const p of partsFmt.formatToParts(d)) if (p.type !== 'literal') out[p.type] = parseInt(p.value)
  if (out.hour === 24) out.hour = 0
  return out
}

/** Unix seconds shifted so lightweight-charts' UTC axis shows ET clock time. */
export function toSecET(t: string): number {
  const g = etParts(new Date(t))
  return Math.floor(Date.UTC(g.year, g.month - 1, g.day, g.hour, g.minute, g.second) / 1000)
}

/** Minutes since midnight ET. */
export function etMinutes(t: string): number {
  const g = etParts(new Date(t))
  return g.hour * 60 + g.minute
}

/** Before 09:30 or at/after 16:00 ET. */
export function isExtended(t: string): boolean {
  const m = etMinutes(t)
  return m < 570 || m >= 960
}

/** Premarket window: 04:00 <= t < 09:30 ET. */
export function isPremarket(t: string): boolean {
  const m = etMinutes(t)
  return m >= 240 && m < 570
}

/** YYYY-MM-DD in ET. */
export function etDate(t: string | Date): string {
  const g = etParts(typeof t === 'string' ? new Date(t) : t)
  return `${g.year}-${String(g.month).padStart(2, '0')}-${String(g.day).padStart(2, '0')}`
}

export function fmtTimeET(t: string, seconds = false): string {
  try {
    return new Date(t).toLocaleTimeString('en-US', {
      timeZone: ET, hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' } : {}), hour12: false,
    })
  } catch { return t }
}

export function nowET(): string {
  return new Date().toLocaleTimeString('en-US', { timeZone: ET, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

/** "3m", "2h", "1d" relative age. */
export function fmtAge(iso: string, now = Date.now()): string {
  const t = new Date(iso).getTime()
  if (!isFinite(t)) return ''
  const s = Math.max(0, (now - t) / 1000)
  if (s < 60) return 'now'
  if (s < 3600) return `${Math.round(s / 60)}m`
  if (s < 86400) return `${Math.round(s / 3600)}h`
  return `${Math.round(s / 86400)}d`
}

/** mm:ss or h:mm:ss countdown. */
export function fmtCountdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`
}
