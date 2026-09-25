import type { Alert } from '../types'
import { useSetups, systemTone } from '../stores/setupsStore'

/** Built-in setups are named and toned from the backend's setup list (by
 *  direction); custom setups use the color chosen in Config > Setups and their
 *  display name. */
export function SetupBadge({ setup, label, color, fallback }: { setup: string | undefined; label?: string; color?: string; fallback?: string }) {
  const custom = useSetups(s => (setup ? s.customById[setup] : undefined))
  const sys = useSetups(s => (setup ? s.systemByCode[setup] : undefined))
  // An alert with no `setup` (only possible in old archives) is named by its
  // trigger, muted, rather than leaving the cell blank.
  if (!setup) return fallback ? <span className="badge muted ellipsis" title={fallback}>{fallback}</span> : null
  if (custom || setup.startsWith('cs_')) {
    const c = color ?? custom?.color ?? 'var(--accent)'
    return <span className="badge custom" style={{ color: c, borderColor: c }} title={setup}>{label ?? custom?.name ?? setup}</span>
  }
  return <span className={`badge sys-${systemTone(sys?.direction)}`} title={setup}>{sys?.name ?? label ?? setup}</span>
}

export function DirBadge({ dir }: { dir: Alert['direction'] }) {
  // Arrow + word + color: direction never depends on hue alone.
  return <span className={`badge ${dir}`}>{dir === 'long' ? '▲ LONG' : dir === 'short' ? '▼ SHORT' : '-'}</span>
}

export function SizePill({ size }: { size?: string }) {
  if (!size) return null
  const label = size === 'full' ? 'FULL' : size === 'three_quarter' ? '3/4' : size === 'half' ? 'HALF' : size
  return <span className="badge muted">{label}</span>
}
