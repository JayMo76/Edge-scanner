import { useMemo, useRef, useState, type ReactNode } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { SortDir } from '../types'

export interface Column<T> {
  id: string
  label: string
  width: string             // CSS grid track, e.g. '64px' or 'minmax(60px,1fr)'
  num?: boolean             // right-aligned mono
  cell(row: T): ReactNode
  sortValue?(row: T): number | string | null
}

export interface VirtualTableProps<T> {
  rows: T[]
  columns: Column<T>[]
  rowKey(row: T): string
  onRowClick?(row: T): void
  onRowDoubleClick?(row: T): void
  rowClass?(row: T): string
  rowStyle?(row: T): React.CSSProperties | undefined
  selectedKey?: string | null
  /** Arrow keys / Home / End move the selection: called with the newly selected row. */
  onSelect?(row: T): void
  defaultSort?: { id: string; dir: SortDir }
  rowHeight?: number
  emptyText?: ReactNode
  /** user-dragged widths (px) by column id; drag the grip at a header's right edge,
   *  double-click it to reset. When given with onColWidths they persist with the window. */
  colWidths?: Record<string, number>
  onColWidths?(w: Record<string, number>): void
}

const MIN_COL_PX = 28

export function VirtualTable<T>({
  rows, columns, rowKey, onRowClick, onRowDoubleClick, rowClass, rowStyle, selectedKey, onSelect, defaultSort, rowHeight = 24, emptyText,
  colWidths, onColWidths,
}: VirtualTableProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null)
  const [sort, setSort] = useState<{ id: string; dir: SortDir } | null>(defaultSort ?? null)
  const [localWidths, setLocalWidths] = useState<Record<string, number>>({})
  const [dragging, setDragging] = useState<string | null>(null)
  const widths = colWidths ?? localWidths
  const setWidths = (w: Record<string, number>) => { if (onColWidths) onColWidths(w); else setLocalWidths(w) }

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find(c => c.id === sort.id)
    if (!col?.sortValue) return rows
    const sv = col.sortValue
    const dir = sort.dir === 'asc' ? 1 : -1
    return rows.slice().sort((a, b) => {
      const va = sv(a), vb = sv(b)
      if (va == null && vb == null) return 0
      if (va == null) return 1
      if (vb == null) return -1
      return (va < vb ? -1 : va > vb ? 1 : 0) * dir
    })
  }, [rows, sort, columns])

  const template = columns.map(c => (widths[c.id] != null ? `${widths[c.id]}px` : c.width)).join(' ')
  const rowVirtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  })

  // Keyboard: the selection is tracked by row key, so it survives sorting and new
  // rows arriving; the arrow keys step from wherever that row currently is.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!onSelect || !sorted.length) return
    const cur = selectedKey == null ? -1 : sorted.findIndex(r => rowKey(r) === selectedKey)
    const page = Math.max(1, Math.floor((parentRef.current?.clientHeight ?? rowHeight * 10) / rowHeight) - 1)
    let next: number
    switch (e.key) {
      case 'ArrowDown': next = cur < 0 ? 0 : cur + 1; break
      case 'ArrowUp': next = cur < 0 ? 0 : cur - 1; break
      case 'PageDown': next = cur + page; break
      case 'PageUp': next = cur - page; break
      case 'Home': next = 0; break
      case 'End': next = sorted.length - 1; break
      default: return
    }
    e.preventDefault()
    next = Math.max(0, Math.min(sorted.length - 1, next))
    onSelect(sorted[next])
    rowVirtualizer.scrollToIndex(next, { align: 'auto' })
  }

  const clickHeader = (c: Column<T>) => {
    if (!c.sortValue) return
    setSort(s => (s?.id === c.id ? { id: c.id, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { id: c.id, dir: 'desc' }))
  }

  // column resize: pointer capture on the grip, width follows the mouse 1:1
  const startResize = (e: React.PointerEvent<HTMLSpanElement>, c: Column<T>) => {
    e.preventDefault(); e.stopPropagation()
    const head = (e.currentTarget.parentElement as HTMLElement)
    const startW = head.getBoundingClientRect().width
    const startX = e.clientX
    const grip = e.currentTarget
    try { grip.setPointerCapture(e.pointerId) } catch { /* ignore */ }
    setDragging(c.id)
    let cur = { ...widths }
    const move = (ev: PointerEvent) => {
      const w = Math.max(MIN_COL_PX, Math.round(startW + ev.clientX - startX))
      cur = { ...cur, [c.id]: w }
      setWidths(cur)
    }
    const up = () => {
      grip.removeEventListener('pointermove', move)
      grip.removeEventListener('pointerup', up)
      grip.removeEventListener('pointercancel', up)
      setDragging(null)
    }
    grip.addEventListener('pointermove', move)
    grip.addEventListener('pointerup', up)
    grip.addEventListener('pointercancel', up)
  }
  const resetWidth = (c: Column<T>) => {
    const next = { ...widths }
    delete next[c.id]
    setWidths(next)
  }

  return (
    <div ref={parentRef} className="tbl wf-nodrag" tabIndex={onSelect ? 0 : undefined} onKeyDown={onSelect ? onKeyDown : undefined}>
      <div className="tbl-head" style={{ gridTemplateColumns: template }}>
        {columns.map(c => (
          <div key={c.id} className={`${c.num ? 'num' : ''}${sort?.id === c.id ? ' sorted' : ''}`} onClick={() => clickHeader(c)}>
            {c.label}{sort?.id === c.id ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
            <span className={`tbl-grip${dragging === c.id ? ' on' : ''}`} title="Drag to resize · double-click to reset"
              onPointerDown={e => startResize(e, c)} onClick={e => e.stopPropagation()} onDoubleClick={e => { e.stopPropagation(); resetWidth(c) }} />
          </div>
        ))}
      </div>
      {sorted.length === 0 ? (
        <div className="wf-empty" style={{ height: 'auto', padding: 24 }}>{emptyText ?? 'Nothing yet'}</div>
      ) : (
        <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
          {rowVirtualizer.getVirtualItems().map(vi => {
            const row = sorted[vi.index]
            const k = rowKey(row)
            return (
              <div
                key={k}
                className={`tbl-row ${rowClass?.(row) ?? ''}${selectedKey === k ? ' sel' : ''}`}
                style={{ gridTemplateColumns: template, position: 'absolute', top: 0, left: 0, right: 0, height: vi.size, transform: `translateY(${vi.start}px)`, ...rowStyle?.(row) }}
                onClick={() => onRowClick?.(row)}
                onDoubleClick={() => onRowDoubleClick?.(row)}
              >
                {columns.map(c => <div key={c.id} className={c.num ? 'num' : ''}>{c.cell(row)}</div>)}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
