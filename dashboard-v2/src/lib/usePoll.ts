import { useCallback, useEffect, useRef, useState } from 'react'

/** Poll `fn` every `intervalMs` while `enabled`; re-runs immediately when `deps` change. */
export function usePoll<T>(fn: () => Promise<T>, intervalMs: number, enabled = true, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const fnRef = useRef(fn)
  useEffect(() => { fnRef.current = fn })
  const gen = useRef(0)

  const refresh = useCallback(async () => {
    const g = ++gen.current
    setLoading(true)
    try {
      const d = await fnRef.current()
      if (g === gen.current) { setData(d); setError(null) }
    } catch (e) {
      if (g === gen.current) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (g === gen.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let stop = false
    const tick = () => { if (!stop) void refresh() }
    tick()
    const onVis = () => { if (document.visibilityState === 'visible') tick() }
    const idt = setInterval(tick, intervalMs)
    document.addEventListener('visibilitychange', onVis)
    return () => { stop = true; clearInterval(idt); document.removeEventListener('visibilitychange', onVis) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs, refresh, ...deps])

  return { data, error, loading, refresh }
}
