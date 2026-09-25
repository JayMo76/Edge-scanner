import { create } from 'zustand'
import type { UniverseMeta } from '../types'
import { api } from '../lib/api'

interface UniverseState {
  symbols: string[]
  meta: Record<string, UniverseMeta>
  loaded: boolean
  load(): Promise<void>
}

export const useUniverse = create<UniverseState>()((set, get) => ({
  symbols: [],
  meta: {},
  loaded: false,
  async load() {
    if (get().loaded) return
    try {
      const d = await api.universeMeta()
      set({ symbols: d.symbols ?? [], meta: d.meta ?? {}, loaded: true })
    } catch {
      // Older scanner without /api/v2: fall back to the plain universe list.
      try {
        const r = await fetch('/api/universe')
        const d = await r.json()
        set({ symbols: d.symbols ?? [], meta: {}, loaded: true })
      } catch { set({ loaded: true }) }
    }
  },
}))
