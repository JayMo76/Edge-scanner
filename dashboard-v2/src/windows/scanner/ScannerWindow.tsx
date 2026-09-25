import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Alert, FeedId, ScannerConfig, ToneName } from '../../types'
import { useFeeds, visibleSources, SOURCE_LABEL, alertKey } from '../../stores/feedsStore'
import { useCapabilities } from '../../stores/capabilitiesStore'
import { useSettings } from '../../stores/settingsStore'
import { useSetups, useSystemSetups } from '../../stores/setupsStore'
import { useScreens } from '../../stores/screensStore'
import { linkAlert } from '../../stores/linkStore'
import { VirtualTable } from '../../components/VirtualTable'
import { ChipMultiSelect, ColumnPicker, Field, Select, Toggle } from '../../components/primitives'
import { SettingsPopup } from '../../components/SettingsPopup'
import { playTone, speak, spellSymbol } from '../../lib/audio'
import { SCANNER_COLUMNS, SCANNER_COLUMN_LIST, filterAlerts, barClose } from './columns'
import { DirBadge } from '../../components/Badge'
import { fmtPrice, fmtX } from '../../lib/format'
import { fmtTimeET } from '../../lib/time'

function ttsText(a: Alert): string {
  return `${spellSymbol(a.symbol)} ${a.direction} ${setupName(a)}`
}

const setupName = (a: Alert) =>
  a.setup_label || (a.setup ? useSetups.getState().label(a.setup) : '') || a.trigger.replace(/_/g, ' ')

/** The alert being inspected, pinned above the table: new rows arriving, sorting
 *  or the row scrolling away never change what this says. */
function SelectedStrip({ a, linked, onClear }: { a: Alert; linked: boolean; onClear(): void }) {
  const rvol = typeof a.context?.rvol === 'number' ? a.context.rvol : a.rvol
  return (
    <div className="sel-strip">
      <DirBadge dir={a.direction} />
      <span className="sym">{a.symbol}</span>
      <span className="what" title={a.trigger_note ?? a.trigger_label ?? undefined}>{setupName(a)}</span>
      <span className="meta mono">{fmtTimeET(barClose(a.timestamp))} ET · {fmtPrice(a.price)}{rvol != null ? ` · RVOL ${fmtX(rvol)}` : ''}</span>
      <span className="flex-spacer" />
      {!linked && <span className="hint" title="Pick a link color on this window so a click drives a chart">not linked to a chart</span>}
      <button className="wf-ctl" title="Clear selection" onClick={onClear}>✕</button>
    </div>
  )
}

/** Setup options for the filter: built-in first by name, then custom (off ones marked). */
function useSetupOptions() {
  const customSetups = useSetups(s => s.custom)
  const systemSetups = useSystemSetups()
  return useMemo(() => [
    ...systemSetups.map(s => ({ value: s.code, label: s.name || s.code })),
    ...customSetups.map(c => ({ value: c.id, label: `${c.name}${c.enabled ? '' : ' (off)'}` })),
  ].sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })), [customSetups, systemSetups])
}

/** The filters you change most, on the window itself: setups, side, columns.
 *  Everything else (sources, score, sound) stays behind the gear. */
function ScannerToolbar({ win, shown }: { win: ScannerConfig; shown: number }) {
  const [pop, setPop] = useState<{ kind: 'setups' | 'columns'; at: DOMRect } | null>(null)
  const options = useSetupOptions()
  const update = (patch: Partial<ScannerConfig>) => useScreens.getState().updateWindow(win.id, patch)
  const open = (kind: 'setups' | 'columns') => (e: React.MouseEvent<HTMLButtonElement>) => {
    const at = e.currentTarget.getBoundingClientRect()
    setPop(p => (p?.kind === kind ? null : { kind, at }))
  }
  const picked = win.setups.length
  const setupsLabel = picked
    ? (picked === 1 ? (options.find(o => o.value === win.setups[0])?.label ?? '1 setup') : `${picked} setups`)
    : win.noSetups ? 'None' : 'All'
  return (
    <div className="wf-toolbar scan-bar">
      <button className={`btn sm${pop?.kind === 'setups' ? ' on' : ''}${!picked && win.noSetups ? ' attn' : ''}`} onClick={open('setups')} title="Which setups this window shows">
        <span className="faint">Setups</span> <b className="ellipsis" style={{ maxWidth: 160 }}>{setupsLabel}</b> <span className="faint">▾</span>
      </button>
      <div className="seg" role="group" aria-label="Side">
        {(['all', 'long', 'short'] as const).map(d => (
          <button key={d} className={win.direction === d ? 'on' : ''} onClick={() => update({ direction: d })}>
            {d === 'all' ? 'All' : d === 'long' ? '▲ Long' : '▼ Short'}
          </button>
        ))}
      </div>
      <button className={`btn sm${pop?.kind === 'columns' ? ' on' : ''}`} onClick={open('columns')} title="Choose and order the columns">
        Columns <span className="faint">▾</span>
      </button>
      <span className="flex-spacer" />
      <span className="faint mono" style={{ fontSize: 11 }}>{shown} shown</span>
      {pop?.kind === 'setups' && (
        <SettingsPopup title="Setups in this window" anchor={pop.at} onClose={() => setPop(null)}>
          <div className="row" style={{ gap: 6, marginBottom: 8 }}>
            <button className={`chip${!picked && !win.noSetups ? ' on' : ''}`} onClick={() => update({ setups: [], noSetups: false })} title="Every setup, including ones added later">All</button>
            <button className={`chip${!picked && win.noSetups ? ' on' : ''}`} onClick={() => update({ setups: [], noSetups: true })}>None</button>
          </div>
          <div className="row wrap" style={{ gap: 4 }}>
            {options.map(o => {
              const on = win.setups.includes(o.value)
              return (
                <button key={o.value} className={`chip${on ? ' on' : ''}`}
                  onClick={() => update({ setups: on ? win.setups.filter(x => x !== o.value) : [...win.setups, o.value], noSetups: true })}>
                  {o.label}
                </button>
              )
            })}
          </div>
        </SettingsPopup>
      )}
      {pop?.kind === 'columns' && (
        <SettingsPopup title="Columns" anchor={pop.at} onClose={() => setPop(null)}>
          <ColumnPicker value={win.columns} onChange={columns => update({ columns })} all={SCANNER_COLUMN_LIST} />
        </SettingsPopup>
      )}
    </div>
  )
}

export function ScannerWindow({ win }: { win: ScannerConfig }) {
  const alerts = useFeeds(s => s.alerts)
  const status = useFeeds(s => s.status)
  const lastSeq = useFeeds(s => s.lastSeq)
  const latest = useFeeds(s => s.latest)
  const globalMute = useSettings(s => s.globalMute)
  const hasSystem = useCapabilities(s => s.system_setups)
  const rows = useMemo(() => filterAlerts(alerts, win, hasSystem), [alerts, win, hasSystem])
  const columns = useMemo(() => win.columns.map(id => SCANNER_COLUMNS[id]).filter(Boolean), [win.columns])
  const mountSeq = useRef(lastSeq)
  const seenSeq = useRef(lastSeq)
  const newKeys = useRef(new Set<string>())
  const [selected, setSelected] = useState<Alert | null>(null)
  const select = (a: Alert) => { setSelected(a); linkAlert(win, a) }

  // sound / TTS on a new alert that passes this window's filter
  useEffect(() => {
    if (lastSeq === seenSeq.current || !latest) return
    seenSeq.current = lastSeq
    if (filterAlerts([latest], win, hasSystem).length === 0) return
    newKeys.current.add(alertKey(latest))
    setTimeout(() => newKeys.current.delete(alertKey(latest)), 2000)
    if (win.muted || globalMute) return
    if (win.sound.tone !== 'off') playTone(win.sound.tone)
    if (win.sound.tts) speak(ttsText(latest), latest.symbol)
  }, [lastSeq, latest, win, globalMute, hasSystem])

  const shownSources = win.sources.filter(s => visibleSources(hasSystem).includes(s))
  const what = shownSources.length ? shownSources.map(s => SOURCE_LABEL[s]).join(' + ') : 'any'
  const empty: ReactNode = !win.setups.length && win.noSetups
    ? 'No setups picked yet. Choose them with Setups ▾ above.'
    : status === 'connected'
    ? (alerts.length ? 'No alerts match the filters' : `No ${what} alerts yet today`)
    : <span className="pulse">Connecting to the scanner feed…</span>

  return (
    <div className="alert-wrap">
    <ScannerToolbar win={win} shown={rows.length} />
    {selected && <SelectedStrip a={selected} linked={win.link !== 'none'} onClear={() => setSelected(null)} />}
    <VirtualTable<Alert>
      rows={rows}
      columns={columns}
      rowKey={alertKey}
      selectedKey={selected ? alertKey(selected) : null}
      onRowClick={select}
      onSelect={select}
      rowClass={a => `${win.rowTint ? (a.direction === 'short' ? 'tint-short' : a.direction === 'long' ? 'tint-long' : '') : ''}${newKeys.current.has(alertKey(a)) && lastSeq > mountSeq.current ? ' row-new' : ''}`}
      emptyText={empty}
      colWidths={win.colWidths}
      onColWidths={colWidths => useScreens.getState().updateWindow(win.id, { colWidths })}
    />
    </div>
  )
}

export function ScannerSettings({ win, onChange }: { win: ScannerConfig; onChange(p: Partial<ScannerConfig>): void }) {
  const counts = useFeeds(s => s.counts)
  const hasSystem = useCapabilities(s => s.system_setups)
  const sources = visibleSources(hasSystem)
  const sourceOptions = sources.map(s => ({ value: s, label: `${SOURCE_LABEL[s]} (${counts[s]})` }))
  return (
    <>
      {/* One source only (no built-in setups on this backend): nothing to pick. */}
      {sources.length > 1 && (
        <Field label="Sources (empty = all)">
          <ChipMultiSelect value={win.sources.filter(s => sources.includes(s))} onChange={next => onChange({ sources: next as FeedId[] })} options={sourceOptions} />
        </Field>
      )}
      <div className="grid2">
        <Field label="Min score"><input className="input" type="number" min={0} max={100} value={win.minScore} onChange={e => onChange({ minScore: Number(e.target.value) || 0 })} /></Field>
        <Field label="Symbol filter"><input className="input mono" style={{ textTransform: 'uppercase' }} value={win.symbolFilter} placeholder="prefix" onChange={e => onChange({ symbolFilter: e.target.value })} /></Field>
        <Field label="Max rows"><input className="input" type="number" min={10} max={5000} value={win.maxRows} onChange={e => onChange({ maxRows: Math.max(10, Number(e.target.value) || 500) })} /></Field>
      </div>
      <div className="faint" style={{ fontSize: 11 }}>Setups, side and columns are on the window's own bar.</div>
      <div className="grid2">
        <Field label="Sound">
          <Select<ToneName> value={win.sound.tone} onChange={tone => { onChange({ sound: { ...win.sound, tone } }); playTone(tone) }}
            options={[{ value: 'off', label: 'Off' }, { value: 'ping', label: 'Ping' }, { value: 'chime', label: 'Chime' }, { value: 'buzz', label: 'Buzz' }]} />
        </Field>
        <Field label="Options">
          <Toggle checked={win.sound.tts} onChange={tts => onChange({ sound: { ...win.sound, tts } })} label="Speak alerts (TTS)" />
          <Toggle checked={win.rowTint} onChange={rowTint => onChange({ rowTint })} label="Tint rows by direction" />
        </Field>
      </div>
    </>
  )
}
