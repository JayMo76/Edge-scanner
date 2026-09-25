import type { ComponentType } from 'react'

/** Optional UI plugins.
 *
 *  Any module in src/plugins/ may export `symbolActions`: small components
 *  rendered next to a ticker wherever the dashboard shows one (alert rows,
 *  rankings, watchlists, stock info). The folder is optional; when it is
 *  absent or empty this list is empty and nothing extra renders. Pair a
 *  plugin with a backend plugin (scanner/plugins.py) when it needs an API. */
export type SymbolAction = ComponentType<{ symbol: string; small?: boolean }>

const modules = import.meta.glob<{ symbolActions?: SymbolAction[] }>('./plugins/*.tsx', { eager: true })

export const SYMBOL_ACTIONS: SymbolAction[] = Object.values(modules).flatMap(m => m.symbolActions ?? [])
