import { useEffect, useMemo, useState } from 'react'
import type { SnapshotRow, WatchlistConfig } from '../../types'
import { api } from '../../lib/api'
import { usePoll } from '../../lib/usePoll'
import { fmtPct, fmtPrice, fmtX, DASH } from '../../lib/format'
import { useWatchlists } from '../../stores/watchlistsStore'
import { useScreens } from '../../stores/screensStore'
import { linkSymbol } from '../../stores/linkStore'
import { VirtualTable, type Column } from '../../components/VirtualTable'
import { ColumnPicker, Empty, Field, Select, SymbolInput, SymbolActions } from '../../components/primitives'
import { WATCHLIST_DEFAULT_COLUMNS } from '../defaults'

interface Row { symbol: string; snap: SnapshotRow | null }
const Pct = ({ v }: { v: number | null | undefined }) => v == null ? <>{DASH}</> : <span className={v > 0 ? 'up' : v < 0 ? 'down' : ''}>{fmtPct(v)}</span>

const ALL_COLUMNS: { id: string; label: string }[] = [
  { id: 'symbol', label: 'Symbol' }, { id: 'price', label: 'Price' }, { id: 'chg', label: '%Chg' }, { id: 'rth', label: '%Open' },
  { id: 'rvol', label: 'RVOL' }, { id: 'vwap', label: 'vs VWAP' }, { id: 'gap', label: 'Gap' }, { id: 'hod', label: 'HOD' }, { id: 'lod', label: 'LOD' },
]

export function WatchlistWindow({ win }: { win: WatchlistConfig }) {
  const lists = useWatchlists(s => s.lists)
  const order = useWatchlists(s => s.order)
  const loaded = useWatchlists(s => s.loaded)
  const { create, setSymbols } = useWatchlists.getState()
  const updateWindow = useScreens(s => s.updateWindow)
  const [drag, setDrag] = useState<string | null>(null)

  // bind to the first list (or create one) when the window has none
  useEffect(() => {
    if (!loaded) return
    if (win.watchlistId && lists[win.watchlistId]) return
    const id = order[0] ?? create('Watchlist')
    updateWindow(win.id, { watchlistId: id })
  }, [loaded, win.watchlistId, win.id, lists, order, create, updateWindow])

  const wl = win.watchlistId ? lists[win.watchlistId] : undefined
  const symbols = useMemo(() => wl?.symbols ?? [], [wl])
  const { data } = usePoll(() => api.snapshot(symbols), 3000, symbols.length > 0, [symbols.join(',')])
  const rows = useMemo<Row[]>(() => symbols.map(s => ({ symbol: s, snap: data?.rows[s] ?? null })), [symbols, data])

  const remove = (sym: string) => wl && setSymbols(wl.id, wl.symbols.filter(s => s !== sym))
  const add = (sym: string) => wl && setSymbols(wl.id, [...wl.symbols, sym])
  const move = (from: string, to: string) => {
    if (!wl || from === to) return
    const arr = wl.symbols.slice()
    const i = arr.indexOf(from), j = arr.indexOf(to)
    if (i < 0 || j < 0) return
    arr.splice(i, 1); arr.splice(j, 0, from)
    setSymbols(wl.id, arr)
  }

  const defs: Record<string, Column<Row>> = {
    symbol: { id: 'symbol', label: 'Symbol', width: 'minmax(84px,1fr)', cell: r => (
      <span className="row" style={{ gap: 4 }} draggable onDragStart={() => setDrag(r.symbol)} onDragOver={e => e.preventDefault()} onDrop={() => { if (drag) move(drag, r.symbol); setDrag(null) }}>
        <span className="faint" style={{ cursor: 'grab' }} title="Drag to reorder">⋮⋮</span><span className="sym">{r.symbol}</span><SymbolActions symbol={r.symbol} />
        <button className="wf-ctl close" style={{ width: 16, height: 16, fontSize: 10 }} title="Remove" onClick={e => { e.stopPropagation(); remove(r.symbol) }}>✕</button>
      </span>) },
    price: { id: 'price', label: 'Price', width: '64px', num: true, cell: r => fmtPrice(r.snap?.price), sortValue: r => r.snap?.price ?? null },
    chg: { id: 'chg', label: '%Chg', width: '62px', num: true, cell: r => <Pct v={r.snap?.chg_pct} />, sortValue: r => r.snap?.chg_pct ?? null },
    rth: { id: 'rth', label: '%Open', width: '62px', num: true, cell: r => <Pct v={r.snap?.rth_chg_pct} />, sortValue: r => r.snap?.rth_chg_pct ?? null },
    rvol: { id: 'rvol', label: 'RVOL', width: '54px', num: true, cell: r => fmtX(r.snap?.rvol), sortValue: r => r.snap?.rvol ?? null },
    vwap: { id: 'vwap', label: 'vs VWAP', width: '64px', num: true, cell: r => <Pct v={r.snap?.dist_vwap_pct} />, sortValue: r => r.snap?.dist_vwap_pct ?? null },
    gap: { id: 'gap', label: 'Gap', width: '58px', num: true, cell: r => <Pct v={r.snap?.gap_pct} />, sortValue: r => r.snap?.gap_pct ?? null },
    hod: { id: 'hod', label: 'HOD', width: '64px', num: true, cell: r => fmtPrice(r.snap?.hod), sortValue: r => r.snap?.hod ?? null },
    lod: { id: 'lod', label: 'LOD', width: '64px', num: true, cell: r => fmtPrice(r.snap?.lod), sortValue: r => r.snap?.lod ?? null },
  }
  const columns = (win.columns.length ? win.columns : WATCHLIST_DEFAULT_COLUMNS).map(c => defs[c]).filter(Boolean)

  if (!loaded) return <Empty title="Loading watchlists…" />
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className="wf-toolbar wf-nodrag">
        <Select value={wl?.id ?? ''} onChange={id => updateWindow(win.id, { watchlistId: id })} options={order.map(id => ({ value: id, label: lists[id]?.name ?? id }))} small />
        <SymbolInput small placeholder="+ add" clearOnCommit onCommit={add} />
        <span className="flex-spacer" />
        <span className="faint" style={{ fontSize: 10.5 }}>{symbols.length} symbols</span>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <VirtualTable<Row> rows={rows} columns={columns} rowKey={r => r.symbol} onRowClick={r => linkSymbol(win, r.symbol, null)}
          emptyText={<span>Empty list. Type a symbol above and press Enter.</span>}
          colWidths={win.colWidths} onColWidths={colWidths => updateWindow(win.id, { colWidths })} />
      </div>
    </div>
  )
}

export function WatchlistSettings({ win, onChange }: { win: WatchlistConfig; onChange(p: Partial<WatchlistConfig>): void }) {
  const lists = useWatchlists(s => s.lists)
  const order = useWatchlists(s => s.order)
  const { create, rename, remove } = useWatchlists.getState()
  const wl = win.watchlistId ? lists[win.watchlistId] : undefined
  const [name, setName] = useState(wl?.name ?? '')
  const [prevName, setPrevName] = useState(wl?.name)
  if (wl?.name !== prevName) { setPrevName(wl?.name); setName(wl?.name ?? '') }
  return (
    <>
      <div className="grid2">
        <Field label="Watchlist"><Select value={wl?.id ?? ''} onChange={id => onChange({ watchlistId: id })} options={order.map(id => ({ value: id, label: lists[id]?.name ?? id }))} /></Field>
        <Field label="Rename">
          <div className="row"><input className="input" value={name} onChange={e => setName(e.target.value)} style={{ flex: 1 }} /><button className="btn sm" onClick={() => wl && rename(wl.id, name)}>Save</button></div>
        </Field>
      </div>
      <div className="row">
        <button className="btn sm" onClick={() => { const n = prompt('New watchlist name', 'Watchlist'); if (n != null) onChange({ watchlistId: create(n) }) }}>+ New list</button>
        <button className="btn sm danger" disabled={!wl} onClick={() => { if (wl && confirm(`Delete "${wl.name}"?`)) { remove(wl.id); onChange({ watchlistId: null }) } }}>Delete list</button>
      </div>
      <Field label="Columns"><ColumnPicker value={win.columns.length ? win.columns : WATCHLIST_DEFAULT_COLUMNS} onChange={columns => onChange({ columns })} all={ALL_COLUMNS} /></Field>
    </>
  )
}
