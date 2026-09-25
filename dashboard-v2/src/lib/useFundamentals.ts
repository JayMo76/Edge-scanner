import { useEffect, useState } from 'react'
import type { Fundamentals } from '../types'
import { api } from './api'

// Shared fundamentals cache (Stock Info, chart logo). yfinance fills the server
// cache in the background; "pending" answers are polled a few times.
const fundCache = new Map<string, Fundamentals>()

export function useFundamentals(symbol: string | null): Fundamentals | null {
  // State is keyed by symbol so a symbol change never needs a synchronous reset.
  const [fetched, setFetched] = useState<{ sym: string; data: Fundamentals } | null>(null)
  useEffect(() => {
    if (!symbol) return
    const hit = fundCache.get(symbol)
    if (hit && hit.ok) return
    let alive = true
    let tries = 0
    const tick = async () => {
      try {
        const d = await api.fundamentals(symbol)
        if (!alive) return
        setFetched({ sym: symbol, data: d })
        if (d.ok || !d.pending) { fundCache.set(symbol, d); return }
      } catch { if (!alive) return }
      // Yahoo can rate-limit for up to 15 min; the server waits it out and fetches,
      // so keep asking: every 5 s at first, then every 30 s for about 25 minutes.
      tries++
      if (tries < 60) setTimeout(tick, tries < 12 ? 5000 : 30000)
    }
    void tick()
    return () => { alive = false }
  }, [symbol])
  if (!symbol) return null
  const cached = fundCache.get(symbol)
  if (cached?.ok) return cached
  return fetched?.sym === symbol ? fetched.data : cached ?? null
}

/** Candidate logo URLs for a company website, best first. */
export function logoUrls(website: string | null | undefined): string[] {
  if (!website) return []
  let host = website.trim()
  try { host = new URL(host.includes('://') ? host : `https://${host}`).hostname } catch { return [] }
  host = host.replace(/^www\./, '')
  if (!host) return []
  // Google's favicon service answers for every domain; Clearbit's logo CDN is
  // higher quality but no longer reliable, so it is only the second try.
  return [
    `https://www.google.com/s2/favicons?domain=${host}&sz=128`,
    `https://logo.clearbit.com/${host}`,
  ]
}
