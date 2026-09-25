import { create } from 'zustand'
import type { ToplistDef, ToplistsPayload } from '../types'
import { api } from '../lib/api'

/** The six server-ranked toplists as Config edits them.
 *
 *  A toplist is not a document you compose: the ranking metric is fixed in the
 *  engine (scanner/toplists.py). What is editable is the scope — which universe
 *  filter it ranks over — and how many rows a new window of it opens with. The
 *  universe assignment is stored with every other assignment under the key
 *  `toplist:<name>`, so the Universe panel's "used by" count includes toplists.
 */
interface ToplistsState {
  loaded: boolean
  error: string | null
  toplists: ToplistDef[]
  byName: Record<string, ToplistDef>
  load(): Promise<void>
  save(name: string, patch: { rows?: number; universe?: string | null }): Promise<void>
}

const apply = (p: ToplistsPayload): Partial<ToplistsState> => ({
  loaded: true, error: null, toplists: p.toplists,
  byName: Object.fromEntries(p.toplists.map(t => [t.name, t])),
})

export const useToplists = create<ToplistsState>()(set => ({
  loaded: false, error: null, toplists: [], byName: {},

  async load() {
    try { set(apply(await api.toplists.get())) }
    catch (e) { set({ error: e instanceof Error ? e.message : String(e) }) }
  },
  async save(name, patch) {
    try { set(apply(await api.toplists.save(name, patch))) }
    catch (e) { set({ error: e instanceof Error ? e.message : String(e) }); throw e }
  },
}))
