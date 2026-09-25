/** Heat cell background: value mapped onto --up / --down (signed) or --accent at variable opacity. */
export function heat(value: number | null | undefined, min: number, max: number, signed = true): string | undefined {
  if (value == null || !isFinite(value)) return undefined
  if (signed) {
    const scale = Math.max(Math.abs(min), Math.abs(max)) || 1
    const k = Math.min(1, Math.abs(value) / scale)
    const pct = Math.round(8 + k * 42)
    return `color-mix(in oklab, var(${value >= 0 ? '--up' : '--down'}) ${pct}%, transparent)`
  }
  const span = (max - min) || 1
  const k = Math.min(1, Math.max(0, (value - min) / span))
  return `color-mix(in oklab, var(--accent) ${Math.round(6 + k * 44)}%, transparent)`
}
