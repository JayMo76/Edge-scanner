import { create } from 'zustand'
import type { ConditionDef, ProfilesPayload, UniverseProfile } from '../types'
import { api } from '../lib/api'

/** Universe profiles (Config > Setups > Universe filters).
 *
 *  A profile is a named AND-list of conditions. Setups point at one, and it is
 *  checked when the setup would fire, before the alert is emitted. Loaded once
 *  at start and refreshed after every save, so the selector on each setup card
 *  and the editor never disagree about what exists.
 */
interface ProfilesState {
  loaded: boolean
  error: string | null
  live: boolean
  universeSize: number
  profiles: UniverseProfile[]
  byId: Record<string, UniverseProfile>
  /** Named reusable lists of DYNAMIC conditions, the mirror of a universe filter. */
  paramSets: UniverseProfile[]
  setById: Record<string, UniverseProfile>
  catalog: ConditionDef[]
  catalogById: Record<string, ConditionDef>
  /** system code / toplist:<name>  ->  profile id */
  assignments: Record<string, string>
  systemKeys: string[]
  /** profile id -> how many symbols pass its static half; null = no static half */
  members: Record<string, number | null>
  stats: ProfilesPayload['stats']
  load(): Promise<void>
  save(p: UniverseProfile): Promise<UniverseProfile>
  remove(id: string): Promise<void>
  saveSet(p: UniverseProfile): Promise<void>
  removeSet(id: string): Promise<void>
  assign(m: Record<string, string | null>): Promise<void>
  /** Display name for a profile id, falling back to the id itself. */
  label(id: string | undefined | null): string
}

const applyPayload = (p: ProfilesPayload): Partial<ProfilesState> => ({
  loaded: true, error: null, live: p.live, universeSize: p.universe_size,
  profiles: p.profiles, byId: Object.fromEntries(p.profiles.map(x => [x.id, x])),
  paramSets: p.parameter_sets ?? [],
  setById: Object.fromEntries((p.parameter_sets ?? []).map(x => [x.id, x])),
  catalog: p.catalog, catalogById: Object.fromEntries(p.catalog.map(c => [c.id, c])),
  assignments: p.assignments, systemKeys: p.system_keys,
  members: p.members, stats: p.stats,
})

export const useProfiles = create<ProfilesState>()((set, get) => ({
  loaded: false, error: null, live: false, universeSize: 0,
  profiles: [], byId: {}, paramSets: [], setById: {}, catalog: [], catalogById: {},
  assignments: {}, systemKeys: [], members: {},
  stats: { since: null, setups: {} },

  async load() {
    try { set(applyPayload(await api.profiles.get())) }
    catch (e) { set({ error: e instanceof Error ? e.message : String(e) }) }
  },
  async save(p) {
    const r = await api.profiles.save(p)
    set(applyPayload(r))
    return r.profile
  },
  async remove(id) {
    set(applyPayload(await api.profiles.delete(id)))
  },
  async saveSet(p) {
    set(applyPayload(await api.profiles.saveSet(p)))
  },
  async removeSet(id) {
    set(applyPayload(await api.profiles.deleteSet(id)))
  },
  async assign(m) {
    set(applyPayload(await api.profiles.assign(m)))
  },
  label(id) {
    if (!id) return 'All symbols'
    return get().byId[id]?.name ?? id
  },
}))
