import { useEffect, useState } from 'react'
import type { NewsConfig, NewsItem } from '../../types'
import { api } from '../../lib/api'
import { usePoll } from '../../lib/usePoll'
import { fmtAge } from '../../lib/time'
import { useLinkedSymbol, linkSymbol } from '../../stores/linkStore'
import { Empty, Field, Select, SymbolInput, Toggle } from '../../components/primitives'
import { ArticleModal } from '../../components/ArticleModal'

export function NewsWindow({ win }: { win: NewsConfig }) {
  const linked = useLinkedSymbol(win, win.symbol)
  const symbol = win.mode === 'linked' ? linked : null
  const enabled = win.mode === 'market' || !!symbol
  const { data, error } = usePoll(() => api.news(symbol ? [symbol] : null, win.limit, win.hours), 60_000, enabled, [symbol, win.limit, win.hours, win.mode])
  const [now, setNow] = useState(() => Date.now())
  const [open, setOpen] = useState<NewsItem | null>(null)
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(t) }, [])

  if (win.mode === 'linked' && !symbol) return <Empty title="No symbol">Link this window to a color group or set a symbol in settings.</Empty>
  if (error && !data) return <Empty title="News unavailable">{error}</Empty>
  const items = data?.items ?? []
  if (data && items.length === 0) return <Empty title={symbol ? `No news for ${symbol}` : 'No market news'}>{`Last ${win.hours}h. ${data.error ?? ''}`}</Empty>

  return (
    <div className="news-list">
      {!!data?.widened_hours && <div className="faint" style={{ padding: '3px 10px', fontSize: 10 }}>Nothing in the last {win.hours}h for {symbol}. Showing the latest from the past {Math.round(data.widened_hours / 24)} days.</div>}
      {data?.stale && <div className="faint" style={{ padding: '3px 10px', fontSize: 10 }}>showing cached news{data.error ? ` (${data.error})` : ''}</div>}
      {items.map(it => (
        <div key={it.id || it.url} className="news-item" style={{ cursor: 'pointer' }} onClick={() => setOpen(it)} title="Open article">
          {win.thumbnails && it.image && <img className="news-thumb" src={it.image} alt="" loading="lazy" />}
          <div style={{ minWidth: 0, flex: 1 }}>
            <span className="news-head">{it.headline}</span>
            <div className="news-meta">
              <span>{it.source}</span><span>·</span><span title={it.created_at}>{fmtAge(it.created_at, now)}</span>
              {it.symbols.slice(0, 6).map(s => (
                <button key={s} className="sym-chip" onClick={e => { e.stopPropagation(); linkSymbol(win, s) }} title={`Link ${s}`}>{s}</button>
              ))}
              <a className="faint" href={it.url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} title="Open original in a new tab" style={{ marginLeft: 'auto', textDecoration: 'none' }}>↗</a>
            </div>
            {it.summary && <div className="news-sum">{it.summary}</div>}
          </div>
        </div>
      ))}
      {open && <ArticleModal item={open} onClose={() => setOpen(null)} onSymbol={s => { linkSymbol(win, s); setOpen(null) }} />}
    </div>
  )
}

export function NewsSettings({ win, onChange }: { win: NewsConfig; onChange(p: Partial<NewsConfig>): void }) {
  return (
    <>
      <div className="grid2">
        <Field label="Mode"><Select value={win.mode} onChange={mode => onChange({ mode })} options={[{ value: 'market', label: 'Market-wide' }, { value: 'linked', label: 'Linked ticker' }]} /></Field>
        <Field label="Symbol (when unlinked)"><SymbolInput value={win.symbol} onCommit={s => onChange({ symbol: s })} /></Field>
        <Field label="Window"><Select value={String(win.hours)} onChange={v => onChange({ hours: Number(v) })} options={[{ value: '6', label: '6 hours' }, { value: '24', label: '24 hours' }, { value: '72', label: '3 days' }, { value: '168', label: '7 days' }]} /></Field>
        <Field label="Items"><Select value={String(win.limit)} onChange={v => onChange({ limit: Number(v) })} options={['20', '50'].map(v => ({ value: v, label: v }))} /></Field>
      </div>
      <Toggle checked={win.thumbnails} onChange={thumbnails => onChange({ thumbnails })} label="Show thumbnails" />
    </>
  )
}
