import { create } from 'zustand'
import type { Alert, LinkColor, WindowBase } from '../types'
import { useScreens } from './screensStore'

type Group = Exclude<LinkColor, 'none'>

interface LinkState {
  symbols: Record<Group, string | null>
  /** The alert last selected in a Scanner window of each group. Charts mark it
   *  while they show its symbol; a symbol typed or clicked elsewhere leaves it
   *  behind (the chart just stops drawing it). */
  alerts: Record<Group, Alert | null>
  setSymbol(color: Group, sym: string | null): void
  setAlert(color: Group, alert: Alert | null): void
}

export const useLinks = create<LinkState>()(set => ({
  symbols: { red: null, green: null, blue: null, yellow: null, purple: null },
  alerts: { red: null, green: null, blue: null, yellow: null, purple: null },
  setSymbol(color, sym) {
    set(s => ({ symbols: { ...s.symbols, [color]: sym ? sym.toUpperCase() : null } }))
  },
  setAlert(color, alert) {
    set(s => ({ alerts: { ...s.alerts, [color]: alert } }))
  },
}))

/** The symbol a window should show: its link group's symbol; while the group has
 *  had no click yet (or the window is unlinked) its own configured symbol. */
export function useLinkedSymbol(win: WindowBase, fallback: string | null): string | null {
  const linked = useLinks(s => (win.link === 'none' ? null : s.symbols[win.link]))
  return win.link === 'none' ? fallback : (linked ?? fallback)
}

/** The selected alert of the window's link group, only while it is for `symbol`. */
export function useLinkedAlert(win: WindowBase, symbol: string | null): Alert | null {
  const a = useLinks(s => (win.link === 'none' ? null : s.alerts[win.link]))
  return a && symbol && a.symbol.toUpperCase() === symbol.toUpperCase() ? a : null
}

/** A window "publishes" a symbol: drives its link group, or (when unlinked) just its own config. */
export function linkSymbol(win: WindowBase, sym: string, ownKey: 'symbol' | null = 'symbol') {
  const s = sym.toUpperCase()
  if (win.link !== 'none') {
    useLinks.getState().setSymbol(win.link, s)
  } else if (ownKey) {
    useScreens.getState().updateWindow(win.id, { [ownKey]: s } as Record<string, unknown>)
  }
}

/** A Scanner window publishes a whole alert: its symbol, plus the event itself for chart markers. */
export function linkAlert(win: WindowBase, alert: Alert) {
  if (win.link === 'none') return
  useLinks.getState().setSymbol(win.link, alert.symbol)
  useLinks.getState().setAlert(win.link, alert)
}
