import { create } from 'zustand'
import type { CustomSetup, SetupsPayload, SystemSetupInfo, TriggerDef } from '../types'
import { api } from '../lib/api'
import { useCapabilities } from './capabilitiesStore'

/** Setups (Config > Setups): the trigger catalog, the system setups' display
 *  names and the custom setups. Loaded once at start and after every save, so
 *  badges, scanner filters and TTS use the same names everywhere. */
interface SetupsState {
  loaded: boolean
  error: string | null
  live: boolean
  catalog: TriggerDef[]
  catalogById: Record<string, TriggerDef>
  /** Built-in setups, in the order the backend gives them. Empty when it has none. */
  system: SystemSetupInfo[]
  systemByCode: Record<string, SystemSetupInfo>
  systemNames: Record<string, string>
  custom: CustomSetup[]
  customById: Record<string, CustomSetup>
  stats: SetupsPayload['stats']
  load(): Promise<void>
  save(s: CustomSetup): Promise<CustomSetup>
  remove(id: string): Promise<void>
  renameSystem(code: string, name: string): Promise<void>
  /** Display name for any setup code / id (badges, TTS, filters). */
  label(setup: string | undefined): string
}

/** Generic tone for a built-in setup, from its direction only. */
export type SystemTone = 'long' | 'short' | 'neutral'
export const systemTone = (direction: string | undefined): SystemTone =>
  direction === 'long' ? 'long' : direction === 'short' ? 'short' : 'neutral'
/** CSS colour for a tone (nav dots, headers). */
export const TONE_COLOR: Record<SystemTone, string> = { long: 'var(--up)', short: 'var(--down)', neutral: 'var(--accent)' }

const applyPayload = (p: SetupsPayload): Partial<SetupsState> => ({
  loaded: true, error: null, live: p.live,
  catalog: p.catalog, catalogById: Object.fromEntries(p.catalog.map(t => [t.id, t])),
  system: p.system ?? [], systemByCode: Object.fromEntries((p.system ?? []).map(s => [s.code, s])),
  systemNames: Object.fromEntries((p.system ?? []).map(s => [s.code, s.name])),
  custom: p.custom, customById: Object.fromEntries(p.custom.map(c => [c.id, c])),
  stats: p.stats,
})

export const useSetups = create<SetupsState>()((set, get) => ({
  loaded: false, error: null, live: false,
  catalog: [], catalogById: {}, system: [], systemByCode: {}, systemNames: {}, custom: [], customById: {},
  stats: { since: null, setups: {} },

  async load() {
    try { set(applyPayload(await api.setups.get())) }
    catch (e) { set({ error: e instanceof Error ? e.message : String(e) }) }
  },
  async save(s) {
    const r = await api.setups.save(s)
    await get().load()
    return r.setup
  },
  async remove(id) {
    await api.setups.delete(id)
    await get().load()
  },
  async renameSystem(code, name) {
    await api.setups.names({ [code]: name })
    await get().load()
  },
  label(setup) {
    if (!setup) return ''
    const st = get()
    return st.customById[setup]?.name ?? st.systemNames[setup] ?? setup
  },
}))

const NO_SYSTEM: SystemSetupInfo[] = []
/** The built-in setups to list in the UI: the backend's list, in its order, and
 *  only when it reports the system_setups capability. Often empty. */
export function useSystemSetups(): SystemSetupInfo[] {
  const has = useCapabilities(s => s.system_setups)
  const list = useSetups(s => s.system)
  return has ? list : NO_SYSTEM
}
