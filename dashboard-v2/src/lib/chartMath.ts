import type { Bar } from '../types'
import { isPremarket } from './time'

export interface Pt { time: number; value: number }
type TS = (t: string) => number

/** Cumulative session VWAP over (h+l+c)/3 * v. Correct only for single-day bar sets. */
export function calcVWAP(bars: Bar[], ts: TS): Pt[] {
  let tpv = 0, vol = 0
  return bars.map(b => {
    tpv += ((b.h + b.l + b.c) / 3) * b.v
    vol += b.v
    return { time: ts(b.t), value: vol > 0 ? tpv / vol : b.c }
  })
}

export function calcSMA(bars: Bar[], period: number, ts: TS): Pt[] {
  const out: Pt[] = []
  let sum = 0
  for (let i = 0; i < bars.length; i++) {
    sum += bars[i].c
    if (i >= period) sum -= bars[i - period].c
    if (i >= period - 1) out.push({ time: ts(bars[i].t), value: sum / period })
  }
  return out
}

export function calcEMA(bars: Bar[], period: number, ts: TS): Pt[] {
  const k = 2 / (period + 1)
  let prev: number | null = null
  return bars.map(b => {
    prev = prev === null ? b.c : b.c * k + prev * (1 - k)
    return { time: ts(b.t), value: prev }
  })
}

/** Latest SMA value over the last `period` closes, or null. */
export function smaLatest(bars: Bar[], period: number): number | null {
  if (bars.length < period) return null
  let s = 0
  for (let i = bars.length - period; i < bars.length; i++) s += bars[i].c
  return s / period
}

/** Premarket high/low from today's intraday bars (04:00-09:29 ET). */
export function pmHighLow(bars: Bar[]): { high: number; low: number } | null {
  let hi = -Infinity, lo = Infinity
  for (const b of bars) if (isPremarket(b.t)) { if (b.h > hi) hi = b.h; if (b.l < lo) lo = b.l }
  return isFinite(hi) && isFinite(lo) ? { high: hi, low: lo } : null
}

/** Prior completed session's high/low/close from daily bars. */
export function priorDayHL(daily: Bar[], todayIso: string): { high: number; low: number; close: number } | null {
  const prior = daily.filter(b => b.t.slice(0, 10) < todayIso)
  const b = prior[prior.length - 1]
  return b ? { high: b.h, low: b.l, close: b.c } : null
}
