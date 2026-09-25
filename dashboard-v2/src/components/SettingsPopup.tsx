import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** Floating settings panel for one window. Rendered in a portal so it sits above
 *  the workspace and the window keeps rendering (and updating) behind it: change a
 *  filter and watch the rows react. Opens anchored under the gear button, drag it
 *  by its header, Esc or Done closes. No dimming backdrop and no outside-click
 *  close, so clicking the window underneath never loses the panel.
 *
 *  Position is derived from the anchor rect alone (captured on the click) and the
 *  height is bounded by maxHeight, so nothing has to be measured after mount. */

const WIDTH = 380
const MARGIN = 8
const MIN_VISIBLE = 240      // keep at least this much panel on screen

interface Props {
  title: string
  /** bounding rect of the button that opened it, in viewport coordinates */
  anchor: DOMRect | null
  onClose(): void
  children: ReactNode
}

function place(x: number, y: number) {
  const maxY = Math.max(MARGIN, window.innerHeight - MIN_VISIBLE - MARGIN)
  const top = Math.min(Math.max(MARGIN, y), maxY)
  return {
    x: Math.min(Math.max(MARGIN, x), Math.max(MARGIN, window.innerWidth - WIDTH - MARGIN)),
    y: top,
    maxHeight: Math.max(MIN_VISIBLE, window.innerHeight - top - MARGIN),
  }
}

export function SettingsPopup({ title, anchor, onClose, children }: Props) {
  const [pos, setPos] = useState(() =>
    place(anchor ? anchor.right - WIDTH : (window.innerWidth - WIDTH) / 2, anchor ? anchor.bottom + 6 : 80))
  const drag = useRef<{ dx: number; dy: number } | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    const onResize = () => setPos(p => place(p.x, p.y))
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('resize', onResize) }
  }, [onClose])

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest('button')) return
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    drag.current = { dx: e.clientX - r.left, dy: e.clientY - r.top }
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* synthetic pointer */ }
    e.preventDefault()
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    setPos(place(e.clientX - d.dx, e.clientY - d.dy))
  }
  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    drag.current = null
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* already released */ }
  }

  return createPortal(
    <div ref={ref} className="wsp wf-nodrag" role="dialog" aria-label={`${title} settings`}
      style={{ left: pos.x, top: pos.y, width: WIDTH, maxHeight: pos.maxHeight }}>
      <div className="wsp-head" title="Drag to move"
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={endDrag} onPointerCancel={endDrag}>
        <span className="wsp-title">{title}</span>
        <span className="faint" style={{ fontSize: 10.5 }}>settings</span>
        <span className="flex-spacer" />
        <button className="wf-ctl" title="Close (Esc)" onClick={onClose}>✕</button>
      </div>
      <div className="wsp-body">{children}</div>
      <div className="wsp-foot">
        <span className="faint" style={{ fontSize: 10.5 }}>Changes apply immediately</span>
        <span className="flex-spacer" />
        <button className="btn sm primary" onClick={onClose}>Done</button>
      </div>
    </div>,
    document.body,
  )
}
