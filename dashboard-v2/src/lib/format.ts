const isNum = (n: unknown): n is number => typeof n === 'number' && isFinite(n)

export const DASH = '—'

export function fmtNum(n: unknown, d = 2): string {
  return isNum(n) ? n.toFixed(d) : DASH
}

/** Prices: 2dp above $1, 4dp below. */
export function fmtPrice(n: unknown): string {
  if (!isNum(n)) return DASH
  return n.toFixed(Math.abs(n) >= 1 ? 2 : 4)
}

export function fmtPct(n: unknown, d = 2, signed = true): string {
  if (!isNum(n)) return DASH
  return `${signed && n > 0 ? '+' : ''}${n.toFixed(d)}%`
}

export function fmtX(n: unknown, d = 1): string {
  return isNum(n) ? `${n.toFixed(d)}x` : DASH
}

/** 1.2M / 340K / 12.5B */
export function fmtVol(n: unknown): string {
  if (!isNum(n)) return DASH
  const a = Math.abs(n)
  if (a >= 1e12) return `${(n / 1e12).toFixed(2)}T`
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(0)}K`
  return n.toFixed(0)
}

export function fmtMoney(n: unknown): string {
  return isNum(n) ? `$${fmtVol(n)}` : DASH
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return DASH
  try {
    return new Date(iso + (iso.length === 10 ? 'T12:00:00' : '')).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } catch { return iso }
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null
  const t = new Date(iso.length === 10 ? iso + 'T12:00:00' : iso).getTime()
  if (!isFinite(t)) return null
  return Math.round((t - Date.now()) / 86400000)
}

export function titleCase(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
