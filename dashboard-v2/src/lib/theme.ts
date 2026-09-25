export type ThemeName = 'navy' | 'daylight'
export const THEMES: { key: ThemeName; label: string; short: string }[] = [
  { key: 'navy', label: 'Navy (dark)', short: '\u263E' },
  { key: 'daylight', label: 'Daylight (light)', short: '\u2600' },
]
// V2 keeps its own key: V1 reads 'scanner-theme' and only knows graphite / warm / daylight.
const KEY = 'scanner-v2-theme'
export const THEME_EVENT = 'scanner-theme'

export function readTheme(): ThemeName {
  try {
    const t = localStorage.getItem(KEY)
    if (t === 'navy' || t === 'daylight') return t
  } catch { /* ignore */ }
  return 'navy'
}

export function applyTheme(t: ThemeName) {
  document.documentElement.setAttribute('data-theme', t)
  try { localStorage.setItem(KEY, t) } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: t }))
}

let probe: HTMLSpanElement | null = null
let cvs: CanvasRenderingContext2D | null = null
const cache = new Map<string, string>()

/** Resolve any CSS color (oklch, color-mix, var()) to a plain rgb()/hex string.
 *  getComputedStyle keeps oklch() as-is in Chromium, and lightweight-charts cannot
 *  parse it, so the value is round-tripped through a canvas which normalises it. */
export function resolveColor(css: string): string {
  const theme = document.documentElement.getAttribute('data-theme') ?? ''
  const key = `${theme}|${css}`
  const hit = cache.get(key)
  if (hit) return hit
  if (!probe) {
    probe = document.createElement('span')
    probe.style.position = 'absolute'
    probe.style.left = '-9999px'
    probe.style.width = '0'
    probe.style.height = '0'
    document.body.appendChild(probe)
  }
  probe.style.color = css
  let out = getComputedStyle(probe).color || css
  if (!/^(rgb|#)/i.test(out)) {
    cvs ??= document.createElement('canvas').getContext('2d', { willReadFrequently: true })
    if (cvs) {
      try {
        cvs.fillStyle = out
        const norm = String(cvs.fillStyle)
        if (/^(rgb|#)/i.test(norm)) out = norm
        else {
          cvs.clearRect(0, 0, 1, 1)
          cvs.fillRect(0, 0, 1, 1)
          const [r, g, b, a] = cvs.getImageData(0, 0, 1, 1).data
          out = `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`
        }
      } catch { /* keep computed value */ }
    }
  }
  cache.set(key, out)
  return out
}

export interface ChartPalette {
  bg: string; text: string; grid: string; border: string
  up: string; down: string; upSoft: string; downSoft: string; accent: string; dim: string
  vwap: string; ema9: string; ema21: string; sma50: string; sma100: string; sma200: string; pd: string; pm: string
}
export function readChartPalette(): ChartPalette {
  const v = (name: string) => resolveColor(`var(${name})`)
  return {
    bg: v('--panel'), text: v('--text-dim'), grid: v('--border-soft'), border: v('--border'),
    up: v('--up'), down: v('--down'), upSoft: v('--up-soft'), downSoft: v('--down-soft'),
    accent: v('--accent'), dim: v('--text-faint'),
    vwap: v('--ind-vwap'), ema9: v('--ind-ema9'), ema21: v('--ind-ema21'),
    sma50: v('--ind-sma50'), sma100: v('--ind-sma100'), sma200: v('--ind-sma200'), pd: v('--ind-pd'), pm: v('--ind-pm'),
  }
}
