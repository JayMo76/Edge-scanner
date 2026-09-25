import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { GridItem, Screen } from '../types'
import { useScreens } from '../stores/screensStore'
import { WindowFrame } from '../windows/WindowFrame'
import { WINDOW_SIZES } from '../windows/defaults'

/**
 * Free-floating window manager. Windows are absolutely positioned inside a fixed,
 * non-scrolling workspace; bounds are stored as workspace fractions (0..1) so a
 * screen keeps its arrangement on any monitor. Drag/resize run on pointer events
 * with pointer capture, mutate the wrapper's style directly inside
 * requestAnimationFrame (the window body never re-renders mid-drag), and commit
 * fractions to the store on pointerup.
 */

const HEAD_PX = 28          // --wf-head-h: the title bar must stay reachable
const KEEP_VISIBLE_PX = 80  // at least this much of the title bar stays inside the workspace
const SNAP_PX = 8
const MIN_W_PX = 160
const MIN_H_PX = 40

type Edge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
const EDGES: Edge[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

interface Px { x: number; y: number; w: number; h: number }
interface DragState {
  mode: 'move' | 'resize'
  edge?: Edge
  id: string
  el: HTMLDivElement
  pointerId: number
  startX: number
  startY: number
  origin: Px
  minW: number
  minH: number
  maxH: number | null
  others: Px[]          // for snapping
  pending: Px | null
  raf: number | null
}

const toPx = (l: GridItem, W: number, H: number): Px =>
  l.maximized ? { x: 0, y: 0, w: W, h: H } : { x: l.x * W, y: l.y * H, w: l.w * W, h: l.h * H }

function snapValue(v: number, targets: number[], enabled: boolean): number {
  if (!enabled) return v
  let best = v, dist = SNAP_PX + 1
  for (const t of targets) {
    const d = Math.abs(t - v)
    if (d < dist) { dist = d; best = t }
  }
  return dist <= SNAP_PX ? best : v
}

export function Workspace({ screen }: { screen: Screen }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const els = useRef(new Map<string, HTMLDivElement>())
  const drag = useRef<DragState | null>(null)
  const [dragging, setDragging] = useState(false)
  const { updateBounds, bringToFront, toggleMaximize, setWorkspaceSize } = useScreens.getState()

  // workspace size -> px conversion; also feeds the store so new windows are sized right
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    // Measure synchronously first so the initial paint does not wait for the
    // observer (which may be delayed while the tab is hidden).
    const first = host.getBoundingClientRect()
    if (first.width > 0 && first.height > 0) {
      setSize({ w: Math.round(first.width), h: Math.round(first.height) })
      setWorkspaceSize(Math.round(first.width), Math.round(first.height))
    }
    const ro = new ResizeObserver(entries => {
      const r = entries[0]?.contentRect
      if (r && r.width > 0 && r.height > 0) {
        setSize({ w: Math.round(r.width), h: Math.round(r.height) })
        setWorkspaceSize(Math.round(r.width), Math.round(r.height))
      }
    })
    ro.observe(host)
    return () => ro.disconnect()
  }, [setWorkspaceSize])

  const W = size.w, H = size.h
  const locked = screen.locked
  const topZ = useMemo(() => screen.layout.reduce((m, l) => Math.max(m, l.z ?? 0), 0), [screen.layout])

  // ── pointer handlers ────────────────────────────────────────────────────

  const applyFrame = (st: DragState) => {
    st.raf = null
    const p = st.pending
    if (!p) return
    st.el.style.transform = `translate(${p.x}px, ${p.y}px)`
    if (st.mode === 'resize') { st.el.style.width = `${p.w}px`; st.el.style.height = `${p.h}px` }
  }

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>, item: GridItem) => {
    if (e.button !== 0) return
    const target = e.target as HTMLElement
    const el = e.currentTarget
    bringToFront(item.i)
    if (locked || item.maximized || W === 0) return
    const handle = target.closest<HTMLElement>('.ws-handle')
    const inDrag = !!target.closest('.wf-drag') && !target.closest('.wf-nodrag')
    if (!handle && !inDrag) return
    const origin = toPx(item, W, H)
    const others = screen.layout.filter(l => l.i !== item.i).map(l => toPx(l, W, H))
    drag.current = {
      mode: handle ? 'resize' : 'move',
      edge: handle ? (handle.dataset.edge as Edge) : undefined,
      id: item.i, el, pointerId: e.pointerId, startX: e.clientX, startY: e.clientY, origin,
      // size limits come from the window TYPE, not from what an old layout stored
      minW: Math.max(MIN_W_PX, WINDOW_SIZES[screen.windows[item.i]?.type]?.minW ?? 0),
      minH: Math.max(MIN_H_PX, WINDOW_SIZES[screen.windows[item.i]?.type]?.minH ?? 0),
      maxH: WINDOW_SIZES[screen.windows[item.i]?.type]?.maxH ?? null,
      others, pending: null, raf: null,
    }
    try { el.setPointerCapture(e.pointerId) } catch { /* synthetic events have no active pointer */ }
    el.classList.add('is-dragging')
    setDragging(true)
    e.preventDefault()
  }, [locked, W, H, screen.layout, screen.windows, bringToFront])

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const st = drag.current
    if (!st || e.pointerId !== st.pointerId) return
    const dx = e.clientX - st.startX, dy = e.clientY - st.startY
    const snapOn = !e.altKey
    const xs = [0, W, ...st.others.flatMap(o => [o.x, o.x + o.w])]
    const ys = [0, H, ...st.others.flatMap(o => [o.y, o.y + o.h])]
    let { x, y, w, h } = st.origin

    if (st.mode === 'move') {
      x += dx; y += dy
      // snap left/right edge, then top/bottom edge
      const sl = snapValue(x, xs, snapOn), sr = snapValue(x + w, xs, snapOn)
      if (sl !== x) x = sl; else if (sr !== x + w) x = sr - w
      const stp = snapValue(y, ys, snapOn), sb = snapValue(y + h, ys, snapOn)
      if (stp !== y) y = stp; else if (sb !== y + h) y = sb - h
      // the title bar can never leave the workspace
      x = Math.min(Math.max(x, -(w - KEEP_VISIBLE_PX)), W - KEEP_VISIBLE_PX)
      y = Math.min(Math.max(y, 0), H - HEAD_PX)
    } else {
      const ed = st.edge ?? 'se'
      let left = x, top = y, right = x + w, bottom = y + h
      if (ed.includes('e')) right = snapValue(Math.min(W, right + dx), xs, snapOn)
      if (ed.includes('w')) left = snapValue(Math.max(0, left + dx), xs, snapOn)
      if (ed.includes('s')) bottom = snapValue(Math.min(H, bottom + dy), ys, snapOn)
      if (ed.includes('n')) top = snapValue(Math.max(0, top + dy), ys, snapOn)
      // enforce min/max by moving the edge that is being dragged
      if (right - left < st.minW) { if (ed.includes('w')) left = right - st.minW; else right = left + st.minW }
      if (bottom - top < st.minH) { if (ed.includes('n')) top = bottom - st.minH; else bottom = top + st.minH }
      if (st.maxH != null && bottom - top > st.maxH) { if (ed.includes('n')) top = bottom - st.maxH; else bottom = top + st.maxH }
      x = left; y = top; w = right - left; h = bottom - top
    }
    st.pending = { x, y, w, h }
    if (st.raf == null) st.raf = requestAnimationFrame(() => applyFrame(st))
  }, [W, H])

  const finish = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const st = drag.current
    if (!st || e.pointerId !== st.pointerId) return
    if (st.raf != null) cancelAnimationFrame(st.raf)
    st.raf = null
    applyFrame(st)
    try { st.el.releasePointerCapture(st.pointerId) } catch { /* already released */ }
    st.el.classList.remove('is-dragging')
    drag.current = null
    setDragging(false)
    const p = st.pending
    if (p && W > 0 && H > 0) {
      updateBounds(st.id, { x: p.x / W, y: p.y / H, w: p.w / W, h: p.h / H })
    }
  }, [W, H, updateBounds])

  const onDoubleClick = useCallback((e: React.MouseEvent<HTMLDivElement>, item: GridItem) => {
    const t = e.target as HTMLElement
    if (locked) return
    if (t.closest('.wf-drag') && !t.closest('.wf-nodrag')) toggleMaximize(item.i)
  }, [locked, toggleMaximize])

  return (
    <div ref={hostRef} className={`ws${locked ? ' locked' : ''}${dragging ? ' dragging' : ''}`}>
      {W > 0 && screen.layout.map(item => {
        const win = screen.windows[item.i]
        if (!win) return null
        const p = toPx(item, W, H)
        return (
          <div
            key={item.i}
            ref={el => { if (el) els.current.set(item.i, el); else els.current.delete(item.i) }}
            className={`ws-win${item.z === topZ ? ' active' : ''}${item.maximized ? ' maximized' : ''}`}
            style={{ transform: `translate(${p.x}px, ${p.y}px)`, width: p.w, height: p.h, zIndex: 10 + (item.z ?? 0) }}
            onPointerDown={e => onPointerDown(e, item)}
            onPointerMove={onPointerMove}
            onPointerUp={finish}
            onPointerCancel={finish}
            onDoubleClick={e => onDoubleClick(e, item)}
          >
            <WindowFrame win={win} locked={locked} maximized={!!item.maximized} onToggleMaximize={() => toggleMaximize(item.i)} />
            {!locked && !item.maximized && EDGES.map(ed => <div key={ed} className={`ws-handle ${ed}`} data-edge={ed} />)}
          </div>
        )
      })}
    </div>
  )
}
