import { useEffect, useRef, type ReactNode } from 'react'

/** Anchored popover menu. Closes on outside click or Escape. Parent must be position:relative. */
export function Menu({ open, onClose, children, right, style }: {
  open: boolean; onClose(): void; children: ReactNode; right?: boolean; style?: React.CSSProperties
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    // defer so the click that opened the menu doesn't immediately close it
    const t = setTimeout(() => { document.addEventListener('mousedown', onDown); document.addEventListener('keydown', onKey) }, 0)
    return () => { clearTimeout(t); document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  if (!open) return null
  return <div ref={ref} className={`menu wf-nodrag${right ? ' right' : ''}`} style={style}>{children}</div>
}

export function MenuItem({ children, onClick, icon, k, on, danger, disabled }: {
  children: ReactNode; onClick?(): void; icon?: string; k?: string; on?: boolean; danger?: boolean; disabled?: boolean
}) {
  return (
    <button className={`menu-item${on ? ' on' : ''}${danger ? ' danger' : ''}`} onClick={onClick} disabled={disabled}>
      {icon !== undefined && <span className="menu-icon">{icon}</span>}
      <span>{children}</span>
      {k && <span className="k">{k}</span>}
    </button>
  )
}

export const MenuSep = () => <div className="menu-sep" />
export const MenuHead = ({ children }: { children: ReactNode }) => <div className="menu-head">{children}</div>
