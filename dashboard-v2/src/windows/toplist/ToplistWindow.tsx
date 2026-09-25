import { useEffect, useMemo, useRef, type ReactNode } from 'react'
import type { HodLodEvent, ToplistConfig, ToplistName, ToplistRow, ToneName } from '../../types'
import { api } from '../../lib/api'
import { usePoll } from '../../lib/usePoll'
import { heat } from '../../lib/colors'
import { fmtPct, fmtPrice, fmtVol, fmtX, DASH } from '../../lib/format'
import { fmtTimeET } from '../../lib/time'
import { playTone, speak, spellSymbol } from '../../lib/audio'
import { useFeeds } from '../../stores/feedsStore'
import { useSettings } from '../../stores/settingsStore'
import { linkSymbol } from '../../stores/linkStore'
import { useScreens } from '../../stores/screensStore'
import { VirtualTable, type Column } from '../../components/VirtualTable'
import { Field, Select, Toggle, SymbolActions } from '../../components/primitives'
import { TOPLIST_LABEL } from '../defaults'

const VALUE_LABEL: Record<ToplistName, string> = {
  rvol: 'RVOL', gainers_close: '%Chg', losers_close: '%Chg', gainers_open: '%Open', losers_open: '%Open',
  movers_5m: '5m %', pm_gainers: 'PM %', pm_losers: 'PM %', pm_volume: 'PM Vol', hod_lod: '',
}
const isPm = (l: ToplistName) => l.startsWith('pm_')

function useToplistRows(win: ToplistConfig): { rows: ToplistRow[]; error: string | null; note?: string } {
  const pm = isPm(win.list)
  const server = usePoll(() => api.toplist(win.list, win.limit), 2000, !pm && win.list !== 'hod_lod', [win.list, win.limit])
  const premarket = usePoll(() => api.premarket(), 30_000, pm, [win.list])
  if (pm) {
    const d = premarket.data
    const key = win.list === 'pm_gainers' ? 'gainers' : win.list === 'pm_losers' ? 'losers' : 'volume'
    const items = d?.[key] ?? []
    return {
      rows: items.slice(0, win.limit).map(i => ({
        symbol: i.symbol, price: i.price, value: win.list === 'pm_volume' ? i.premarket_volume : i.change_pct,
        chg_pct: i.change_pct, rvol: null, volume: i.premarket_volume,
      })),
      error: premarket.error ?? d?.error ?? null,
      note: d?.fetched_at ? `as of ${d.fetched_at}` : undefined,
    }
  }
  return { rows: server.data?.rows ?? [], error: server.error }
}

function HodLodTable({ win }: { win: ToplistConfig }) {
  const events = useFeeds(s => s.events)
  const acquire = useFeeds(s => s.acquireEvents)
  const globalMute = useSettings(s => s.globalMute)
  const lastSeq = useRef(0)
  useEffect(() => acquire(), [acquire])
  useEffect(() => {
    const top = events[0]
    if (!top || top.seq <= lastSeq.current) return
    const first = lastSeq.current === 0
    lastSeq.current = top.seq
    if (first || win.muted || globalMute) return
    if (win.sound.tone !== 'off') playTone(win.sound.tone)
    if (win.sound.tts) speak(`${spellSymbol(top.symbol)} new ${top.type === 'HOD' ? 'high' : 'low'}`, top.symbol)
  }, [events, win.muted, win.sound, globalMute])
  const rows = useMemo(() => events.slice(0, win.limit), [events, win.limit])
  const cols: Column<HodLodEvent>[] = [
    { id: 'time', label: 'Time', width: '52px', cell: e => <span className="mono dim">{fmtTimeET(e.ts)}</span> },
    { id: 'type', label: '', width: '48px', cell: e => <span className={`badge ${e.type.toLowerCase()}`}>{e.type}</span> },
    { id: 'symbol', label: 'Symbol', width: 'minmax(70px,1fr)', cell: e => <span className="row" style={{ gap: 4 }}><span className="sym">{e.symbol}</span><SymbolActions symbol={e.symbol} /></span> },
    { id: 'price', label: 'Price', width: '68px', num: true, cell: e => fmtPrice(e.price) },
  ]
  return (
    <VirtualTable<HodLodEvent> rows={rows} columns={cols} rowKey={e => String(e.seq)} onRowClick={e => linkSymbol(win, e.symbol, null)}
      rowClass={e => `${e.type === 'HOD' ? 'tint-long' : 'tint-short'}${e.seq > lastSeq.current - 3 ? ' row-new' : ''}`}
      emptyText="No new highs or lows yet (RTH only)" />
  )
}

export function ToplistWindow({ win }: { win: ToplistConfig }) {
  if (win.list === 'hod_lod') return <HodLodTable win={win} />
  return <RankedTable win={win} />
}

function RankedTable({ win }: { win: ToplistConfig }) {
  const { rows, error, note } = useToplistRows(win)
  const { min, max } = useMemo(() => {
    const vals = rows.map(r => r.value).filter((v): v is number => v != null)
    return { min: Math.min(0, ...vals), max: Math.max(0, ...vals) }
  }, [rows])
  const signed = !['rvol', 'pm_volume'].includes(win.list)
  const fmtValue = (v: number | null) => v == null ? DASH : win.list === 'rvol' ? fmtX(v, 2) : win.list === 'pm_volume' ? fmtVol(v) : fmtPct(v, 2)
  const cols: Column<ToplistRow>[] = [
    { id: 'rank', label: '#', width: '26px', num: true, cell: r => <span className="faint">{rows.indexOf(r) + 1}</span> },
    { id: 'symbol', label: 'Symbol', width: 'minmax(66px,1fr)', cell: r => <span className="row" style={{ gap: 4 }}><span className="sym">{r.symbol}</span><SymbolActions symbol={r.symbol} /></span>, sortValue: r => r.symbol },
    { id: 'price', label: 'Price', width: '64px', num: true, cell: r => fmtPrice(r.price), sortValue: r => r.price },
    { id: 'value', label: VALUE_LABEL[win.list], width: '70px', num: true, cell: r => <span className={signed && r.value != null ? (r.value > 0 ? 'up' : r.value < 0 ? 'down' : '') : ''} style={{ fontWeight: 600 }}>{fmtValue(r.value)}</span>, sortValue: r => r.value },
    { id: 'chg', label: '%Chg', width: '62px', num: true, cell: r => <span className={r.chg_pct != null ? (r.chg_pct > 0 ? 'up' : r.chg_pct < 0 ? 'down' : '') : ''}>{fmtPct(r.chg_pct)}</span>, sortValue: r => r.chg_pct },
    { id: 'rvol', label: 'RVOL', width: '54px', num: true, cell: r => fmtX(r.rvol), sortValue: r => r.rvol },
  ]
  const empty: ReactNode = error
    ? <span className="down">{error}</span>
    : isPm(win.list) ? 'No pre-market data (before 04:00 ET, or nothing traded yet)'
    : ['gainers_open', 'losers_open', 'movers_5m', 'rvol'].includes(win.list) ? 'Waiting for the open' : 'No data'
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <VirtualTable<ToplistRow> rows={rows} columns={cols} rowKey={r => r.symbol} onRowClick={r => linkSymbol(win, r.symbol, null)}
          rowStyle={r => (win.heat ? { background: heat(r.value, min, max, signed) } : undefined)} emptyText={empty}
          colWidths={win.colWidths} onColWidths={colWidths => useScreens.getState().updateWindow(win.id, { colWidths })} />
      </div>
      {note && <div className="faint" style={{ padding: '2px 8px', fontSize: 10, borderTop: '1px solid var(--border-soft)' }}>{note}</div>}
    </div>
  )
}

export function ToplistSettings({ win, onChange }: { win: ToplistConfig; onChange(p: Partial<ToplistConfig>): void }) {
  return (
    <>
      <div className="grid2">
        <Field label="List">
          <Select<ToplistName> value={win.list} onChange={list => onChange({ list })} options={(Object.keys(TOPLIST_LABEL) as ToplistName[]).map(k => ({ value: k, label: TOPLIST_LABEL[k] }))} />
        </Field>
        <Field label="Rows"><Select value={String(win.limit)} onChange={v => onChange({ limit: Number(v) })} options={['10', '25', '50', '100'].map(v => ({ value: v, label: v }))} /></Field>
      </div>
      <Toggle checked={win.heat} onChange={heat => onChange({ heat })} label="Heat-color the value column" />
      {win.list === 'hod_lod' && (
        <div className="grid2">
          <Field label="Sound"><Select<ToneName> value={win.sound.tone} onChange={tone => { onChange({ sound: { ...win.sound, tone } }); playTone(tone) }} options={[{ value: 'off', label: 'Off' }, { value: 'ping', label: 'Ping' }, { value: 'chime', label: 'Chime' }, { value: 'buzz', label: 'Buzz' }]} /></Field>
          <Field label="Voice"><Toggle checked={win.sound.tts} onChange={tts => onChange({ sound: { ...win.sound, tts } })} label="Speak new highs / lows" /></Field>
        </div>
      )}
      <div className="faint" style={{ fontSize: 11 }}>Lists cover the scanner's universe (~237 symbols), not the whole market.</div>
    </>
  )
}
