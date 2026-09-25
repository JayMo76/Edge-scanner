import { useEffect, useMemo } from 'react'
import { createPortal } from 'react-dom'
import type { NewsItem } from '../types'
import { resolveColor } from '../lib/theme'
import { fmtAge } from '../lib/time'

/** Full-article popup. The wire's HTML is rendered inside a sandboxed iframe
 *  (no scripts, no same-origin), so nothing in an article can touch the app. */
export function ArticleModal({ item, onClose, onSymbol }: { item: NewsItem; onClose(): void; onSymbol?(sym: string): void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const srcdoc = useMemo(() => {
    const v = (n: string) => resolveColor(`var(${n})`)
    const body = item.content?.trim()
      ? item.content
      : `<p>${escapeHtml(item.summary || 'No article body was included with this story.')}</p>`
    return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank">
<style>
  body{margin:0;padding:18px 22px 28px;background:${v('--panel')};color:${v('--text')};
       font:14px/1.6 "IBM Plex Sans",system-ui,sans-serif;word-wrap:break-word}
  img,video,iframe{max-width:100%;height:auto}
  a{color:${v('--accent')}} h1,h2,h3{line-height:1.25} blockquote{border-left:3px solid ${v('--border')};margin:0;padding-left:12px;color:${v('--text-dim')}}
  table{border-collapse:collapse} td,th{border:1px solid ${v('--border')};padding:4px 8px}
  pre{white-space:pre-wrap}
</style></head><body>${body}</body></html>`
  }, [item])

  // Portal to <body>: grid windows are positioned with CSS transforms, which
  // would otherwise trap this fixed overlay inside the window's own box.
  return createPortal(
    <div className="modal-back" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal wf-nodrag" role="dialog" aria-modal="true">
        <div className="modal-head">
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="modal-title">{item.headline}</div>
            <div className="news-meta" style={{ marginTop: 4 }}>
              <span>{item.source}</span><span>·</span><span title={item.created_at}>{fmtAge(item.created_at)} ago</span>
              {item.symbols.slice(0, 8).map(s => (
                <button key={s} className="sym-chip" onClick={() => onSymbol?.(s)} title={`Link ${s}`}>{s}</button>
              ))}
            </div>
          </div>
          <a className="btn sm" href={item.url} target="_blank" rel="noopener noreferrer" title="Open the original article in a new tab">Open original ↗</a>
          <button className="btn sm icon" title="Close (Esc)" onClick={onClose}>✕</button>
        </div>
        {item.image && <img className="modal-hero" src={item.image} alt="" />}
        <iframe className="modal-body" title={item.headline} sandbox="" srcDoc={srcdoc} />
      </div>
    </div>,
    document.body,
  )
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))
}
