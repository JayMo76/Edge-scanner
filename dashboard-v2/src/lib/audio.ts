import type { ToneName } from '../types'

// No asset files: tones are synthesised so nothing depends on the /v2/ base
// path, and TTS uses the browser's built-in voices.

let ctx: AudioContext | null = null
export function audioReady(): boolean { return !!ctx && ctx.state === 'running' }
export async function unlockAudio(): Promise<boolean> {
  try {
    ctx ??= new AudioContext()
    if (ctx.state !== 'running') await ctx.resume()
    try { window.speechSynthesis?.getVoices() } catch { /* ignore */ }
    return ctx.state === 'running'
  } catch { return false }
}

const PRESETS: Record<Exclude<ToneName, 'off'>, { f: number[]; dur: number; type: OscillatorType }> = {
  ping: { f: [880], dur: 0.14, type: 'sine' },
  chime: { f: [660, 990], dur: 0.22, type: 'triangle' },
  buzz: { f: [220, 196], dur: 0.18, type: 'square' },
}

export function playTone(name: ToneName, gain = 0.18) {
  if (name === 'off' || !ctx || ctx.state !== 'running') return
  const c = ctx
  const p = PRESETS[name]
  const t0 = c.currentTime
  p.f.forEach((freq, i) => {
    const osc = c.createOscillator()
    const g = c.createGain()
    osc.type = p.type
    osc.frequency.value = freq
    const start = t0 + i * (p.dur * 0.6)
    g.gain.setValueAtTime(0, start)
    g.gain.linearRampToValueAtTime(gain, start + 0.01)
    g.gain.exponentialRampToValueAtTime(0.0001, start + p.dur)
    osc.connect(g).connect(c.destination)
    osc.start(start)
    osc.stop(start + p.dur + 0.02)
  })
}

// ── TTS with a token bucket (max 4 utterances / 10 s) and per-symbol dedup ──
const MAX_PER_WINDOW = 4
const WINDOW_MS = 10_000
const DEDUP_MS = 5_000
let stamps: number[] = []
const lastBySymbol = new Map<string, number>()
let queue: string[] = []
let speaking = false

function pump() {
  if (speaking || queue.length === 0) return
  const synth = window.speechSynthesis
  if (!synth) { queue = []; return }
  const text = queue.shift()!
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 1.05
  speaking = true
  u.onend = () => { speaking = false; pump() }
  u.onerror = () => { speaking = false; pump() }
  synth.speak(u)
}

/** Speak `text`; `symbol` dedups repeats within 5 s; rate limited to 4 per 10 s. */
export function speak(text: string, symbol?: string): boolean {
  const now = Date.now()
  stamps = stamps.filter(t => now - t < WINDOW_MS)
  if (stamps.length >= MAX_PER_WINDOW) return false
  if (symbol) {
    const last = lastBySymbol.get(symbol)
    if (last && now - last < DEDUP_MS) return false
    lastBySymbol.set(symbol, now)
  }
  stamps.push(now)
  queue.push(text)
  pump()
  return true
}

export function cancelSpeech() {
  queue = []
  try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
  speaking = false
}

/** "M S F T" so the voice spells the ticker instead of guessing a word. */
export function spellSymbol(sym: string): string { return sym.split('').join(' ') }
