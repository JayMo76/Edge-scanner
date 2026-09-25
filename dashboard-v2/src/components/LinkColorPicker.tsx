import { useState } from 'react'
import { LINK_COLORS, type LinkColor } from '../types'
import { Menu } from './Menu'

export function LinkDot({ color, onClick, title }: { color: LinkColor; onClick?(): void; title?: string }) {
  return <button className={`link-dot ${color}`} onClick={onClick} title={title ?? (color === 'none' ? 'Not linked' : `Link group: ${color}`)} />
}

export function LinkColorPicker({ value, onChange }: { value: LinkColor; onChange(c: LinkColor): void }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ position: 'relative', display: 'flex' }} className="wf-nodrag">
      <LinkDot color={value} onClick={() => setOpen(o => !o)} />
      <Menu open={open} onClose={() => setOpen(false)} style={{ left: -6, minWidth: 0 }}>
        <div className="link-picker">
          <button className={`link-dot none${value === 'none' ? ' sel' : ''}`} title="Unlink" onClick={() => { onChange('none'); setOpen(false) }} />
          {LINK_COLORS.map(c => (
            <button key={c} className={`link-dot ${c}${value === c ? ' sel' : ''}`} title={c} onClick={() => { onChange(c); setOpen(false) }} />
          ))}
        </div>
      </Menu>
    </div>
  )
}
