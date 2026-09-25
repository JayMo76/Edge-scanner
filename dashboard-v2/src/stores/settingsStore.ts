import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { applyTheme, readTheme, type ThemeName } from '../lib/theme'
import { cancelSpeech } from '../lib/audio'

interface SettingsState {
  theme: ThemeName
  menuHidden: boolean
  globalMute: boolean
  setTheme(t: ThemeName): void
  cycleTheme(): void
  setMenuHidden(v: boolean): void
  setGlobalMute(v: boolean): void
}

export const useSettings = create<SettingsState>()(
  persist(
    (set, get) => ({
      theme: readTheme(),
      menuHidden: false,
      globalMute: false,
      setTheme(t) { applyTheme(t); set({ theme: t }) },
      cycleTheme() {
        const order: ThemeName[] = ['navy', 'daylight']
        const next = order[(order.indexOf(get().theme) + 1) % order.length]
        get().setTheme(next)
      },
      setMenuHidden(v) { set({ menuHidden: v }) },   // the Workspace observes its own size
      setGlobalMute(v) { if (v) cancelSpeech(); set({ globalMute: v }) },
    }),
    {
      name: 'scanner-v2-settings',
      partialize: s => ({ theme: s.theme, menuHidden: s.menuHidden, globalMute: s.globalMute }),
      onRehydrateStorage: () => state => {
        if (!state) return
        // older persisted values (graphite / warm) collapse onto the navy theme
        const t = (state.theme as string) === 'daylight' ? 'daylight' : 'navy'
        state.theme = t
        applyTheme(t)
      },
    },
  ),
)
