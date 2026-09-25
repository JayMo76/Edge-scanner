import { create } from 'zustand'
import { api } from '../lib/api'

/** What the running backend offers beyond the core scanner.
 *
 *  The same dashboard ships against backends with and without these, so every
 *  optional piece of UI asks here instead of assuming. Loaded once at startup;
 *  a failed request (an older backend, a network error) means "none of them". */
interface CapabilitiesState {
  /** The backend provides built-in setups from an engine plugin. */
  system_setups: boolean
  /** Every flag the backend reported, for UI plugins (src/plugins/) to read. */
  flags: Record<string, boolean>
  loaded: boolean
  load(): Promise<void>
}

export const useCapabilities = create<CapabilitiesState>()(set => ({
  system_setups: false,
  flags: {},
  loaded: false,
  async load() {
    try {
      const c = await api.capabilities()
      const flags = Object.fromEntries(Object.entries(c ?? {}).map(([k, v]) => [k, v === true]))
      set({ system_setups: flags.system_setups === true, flags, loaded: true })
    } catch {
      set({ system_setups: false, flags: {}, loaded: true })
    }
  },
}))
