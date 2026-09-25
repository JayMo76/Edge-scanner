import type { ReactNode } from 'react'
import type { Alert, ScannerConfig } from '../../types'
import type { Column } from '../../components/VirtualTable'
import { SetupBadge, DirBadge, SizePill } from '../../components/Badge'
import { SymbolActions } from '../../components/primitives'
import { fmtNum, fmtPct, fmtPrice, fmtX, DASH } from '../../lib/format'
import { SOURCE_SHORT, sourceOf } from '../../stores/feedsStore'
import { fmtTimeET } from '../../lib/time'

// Column definitions and the per-window filter for the Scanner window. Kept out of
// ScannerWindow.tsx so that file exports only components (fast-refresh rule).

/** When the bar an alert fired on CLOSED.
 *
 *  `alert.timestamp` is the bar's START, which is Alpaca's convention and every
 *  chart's: a bar labelled 15:30 covers 15:30:00-15:30:59 and cannot exist until
 *  15:31:00. Showing the start made the scanner look a minute behind when it was
 *  actually publishing 1-5 seconds after the close. Every evaluator runs on
 *  1-minute bars, so the close is always the start plus one minute.
 *
 *  The payload is untouched: downstream clients still read `timestamp`.
 */
export const barClose = (iso: string): string => {
  const t = Date.parse(iso)
  return Number.isNaN(t) ? iso : new Date(t + 60_000).toISOString()
}

/** Display name for an alert with no `setup` of its own (old archives only). */
const feedSetupName = (a: Alert): string | undefined =>
  a.setup ? undefined : a.trigger?.replace(/_/g, ' ')

const ctxNum = (a: Alert, k: string): number | null => {
  const v = a.context?.[k]
  return typeof v === 'number' ? v : null
}
const condNum = (a: Alert, k: string): number | null => {
  const v = a.conditions?.[k]?.value
  return typeof v === 'number' ? v : null
}

// plain helper (not a component) so this file stays fast-refresh friendly
const pct = (v: number | null, d = 2): ReactNode =>
  v == null ? DASH : <span className={v > 0 ? 'up' : v < 0 ? 'down' : ''}>{fmtPct(v, d)}</span>

export const SCANNER_COLUMNS: Record<string, Column<Alert>> = {
  source: { id: 'source', label: 'Src', width: '40px', cell: a => <span className={`badge src-${sourceOf(a)}`} title={sourceOf(a)}>{SOURCE_SHORT[sourceOf(a)]}</span>, sortValue: a => sourceOf(a) },
  time: { id: 'time', label: 'Time', width: '52px', cell: a => <span className="mono dim" title={`bar ${fmtTimeET(a.timestamp)}-${fmtTimeET(barClose(a.timestamp))}`}>{fmtTimeET(barClose(a.timestamp))}</span>, sortValue: a => a.timestamp },
  symbol: { id: 'symbol', label: 'Symbol', width: '96px', cell: a => <span className="row" style={{ gap: 4 }}><span className="sym">{a.symbol}</span><SymbolActions symbol={a.symbol} /></span>, sortValue: a => a.symbol },
  dir: { id: 'dir', label: 'Side', width: '68px', cell: a => <DirBadge dir={a.direction} />, sortValue: a => a.direction },
  price: { id: 'price', label: 'Price', width: '64px', num: true, cell: a => fmtPrice(a.price), sortValue: a => a.price },
  setup: { id: 'setup', label: 'Setup', width: 'minmax(150px, 2fr)', cell: a => <SetupBadge setup={a.setup} label={a.setup_label} color={a.setup_color} fallback={feedSetupName(a)} />, sortValue: a => a.setup_label ?? a.setup ?? feedSetupName(a) ?? '' },
  tier: { id: 'tier', label: 'Tier', width: '40px', num: true, cell: a => (a.tier == null ? DASH : String(a.tier)), sortValue: a => a.tier ?? null },
  trigger: { id: 'trigger', label: 'Trigger', width: 'minmax(90px, 1.2fr)', cell: a => <span className="dim ellipsis" title={a.trigger_note ?? undefined}>{a.custom ? (a.trigger_note || a.trigger_label || a.entry_trigger) : (a.entry_trigger?.replace(/_/g, ' ') ?? a.trigger)}</span>, sortValue: a => a.trigger },
  score: { id: 'score', label: 'Score', width: '48px', num: true, cell: a => <b>{a.score}</b>, sortValue: a => a.score },
  rvol: { id: 'rvol', label: 'RVOL', width: '54px', num: true, cell: a => fmtX(ctxNum(a, 'rvol') ?? a.rvol ?? condNum(a, 'rvol')), sortValue: a => ctxNum(a, 'rvol') ?? a.rvol ?? condNum(a, 'rvol') },
  gap: { id: 'gap', label: 'Gap', width: '58px', num: true, cell: a => pct(ctxNum(a, 'gap_pct'), 1), sortValue: a => ctxNum(a, 'gap_pct') },
  rs: { id: 'rs', label: 'RS', width: '58px', num: true, cell: a => pct(ctxNum(a, 'rs_vs_spy_pct')), sortValue: a => ctxNum(a, 'rs_vs_spy_pct') },
  rrs: { id: 'rrs', label: 'RRS', width: '50px', num: true, cell: a => fmtNum(condNum(a, 'rrs_d1'), 1), sortValue: a => condNum(a, 'rrs_d1') },
  pct_change: { id: 'pct_change', label: '%Chg', width: '60px', num: true, cell: a => pct(a.pct_change == null ? null : a.pct_change * 100, 1), sortValue: a => a.pct_change ?? null },
  stop: { id: 'stop', label: 'Stop', width: '96px', num: true, cell: a => (a.suggested_stop == null ? DASH : <span className={a.stop_ok === false ? 'down' : ''}>{fmtPrice(a.suggested_stop)} <span className="faint">({fmtNum(a.stop_pct)}%)</span></span>), sortValue: a => a.stop_pct ?? null },
  size: { id: 'size', label: 'Size', width: '48px', cell: a => <SizePill size={a.size_hint} />, sortValue: a => a.size_hint ?? '' },
  vwap: { id: 'vwap', label: 'vs VWAP', width: '62px', num: true, cell: a => pct(ctxNum(a, 'dist_vwap_pct')), sortValue: a => ctxNum(a, 'dist_vwap_pct') },
  mom15: { id: 'mom15', label: '15m', width: '56px', num: true, cell: a => pct(ctxNum(a, 'mom_15m_pct')), sortValue: a => ctxNum(a, 'mom_15m_pct') },
  regime: { id: 'regime', label: 'Regime', width: '62px', cell: a => <span className="dim">{a.market_regime}</span>, sortValue: a => a.market_regime },
  warn: { id: 'warn', label: 'Flags', width: '54px', cell: a => {
    const n = a.warnings?.length ?? 0
    const wide = a.stop_ok === false
    return <span className="row" style={{ gap: 3 }}>{a.fresh_break && <span className="badge long" title="Fresh break">F</span>}{wide && <span className="badge short" title="Stop wider than cap">W</span>}{a.modified && <span className="badge muted" style={{ color: 'var(--accent)' }} title={`Fired under edited settings (config ${a.config_hash})`}>CFG</span>}{n > 0 && <span className="badge muted" title={a.warnings!.join('\n')}>{n}</span>}</span>
  } },
}
export const SCANNER_COLUMN_LIST = Object.values(SCANNER_COLUMNS).map(c => ({ id: c.id, label: c.label }))

/** `hasSystem` is capabilities.system_setups: without it a saved 'system'
 *  source is ignored (as if it were not in the list). */
export function filterAlerts(alerts: Alert[], win: ScannerConfig, hasSystem = true): Alert[] {
  const q = win.symbolFilter.trim().toUpperCase()
  const sources = hasSystem ? win.sources : win.sources.filter(s => s !== 'system')
  const out: Alert[] = []
  // Empty setups normally means all; a window with none picked yet shows nothing.
  if (!win.setups.length && win.noSetups) return out
  for (const a of alerts) {
    if (sources.length && !sources.includes(sourceOf(a))) continue
    // setups filter: system setup codes and custom setup ids. Empty = all.
    if (win.setups.length && !(a.setup && win.setups.includes(a.setup))) continue
    if (win.direction !== 'all' && a.direction !== win.direction) continue
    if (win.minScore > 0 && (a.score ?? 0) < win.minScore) continue
    if (q && !a.symbol.startsWith(q)) continue
    out.push(a)
    if (out.length >= win.maxRows) break
  }
  return out
}
