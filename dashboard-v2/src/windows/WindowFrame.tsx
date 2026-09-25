import { Component, useState, type ReactNode } from 'react'
import type { LinkColor, WindowConfig } from '../types'
import { useScreens } from '../stores/screensStore'
import { useLinks } from '../stores/linkStore'
import { WINDOW_REGISTRY } from './registry'
import { LinkColorPicker } from '../components/LinkColorPicker'
import { SettingsPopup } from '../components/SettingsPopup'
import { USES_LINK, USES_SOUND, WINDOW_ICONS, WINDOW_TITLES } from './defaults'

class WindowErrorBoundary extends Component<{ children: ReactNode; name: string }, { error: string | null }> {
  state = { error: null as string | null }
  static getDerivedStateFromError(e: unknown) { return { error: e instanceof Error ? e.message : String(e) } }
  render() {
    if (this.state.error) {
      return (
        <div className="wf-error">
          <b>{this.props.name} crashed.</b> {this.state.error}
          <div style={{ marginTop: 8 }}><button className="btn sm" onClick={() => this.setState({ error: null })}>Retry</button></div>
        </div>
      )
    }
    return this.props.children
  }
}

interface Props {
  win: WindowConfig
  locked: boolean
  maximized?: boolean
  onToggleMaximize?(): void
}

/** Chrome around every window. The title bar (.wf-drag) is the drag handle; anything
 *  marked .wf-nodrag (controls, body) is not. Positioning is the Workspace's job. */
export function WindowFrame({ win, locked, maximized = false, onToggleMaximize }: Props) {
  // the gear button's rect, captured on click, positions the pop-up; null = closed
  const [settingsAt, setSettingsAt] = useState<DOMRect | null>(null)
  const updateWindow = useScreens(s => s.updateWindow)
  const removeWindow = useScreens(s => s.removeWindow)
  const linkedSymbol = useLinks(s => (win.link === 'none' ? null : s.symbols[win.link]))
  const def = WINDOW_REGISTRY[win.type]
  const Body = def.component
  const Settings = def.settings
  const title = win.title || WINDOW_TITLES[win.type]
  const sub = def.subtitle?.(win, linkedSymbol)
  // Click the title text to rename the window. The text is .wf-nodrag: the drag
  // code captures the pointer, which would swallow the click. The rest of the bar drags.
  const [renaming, setRenaming] = useState<string | null>(null)
  const commitTitle = () => {
    if (renaming == null) return
    const t = renaming.trim()
    updateWindow(win.id, { title: t && t !== WINDOW_TITLES[win.type] ? t : undefined })
    setRenaming(null)
  }

  return (
    <div className={`wf link-${win.link}`}>
      <div className="wf-head">
        {USES_LINK[win.type] && <LinkColorPicker value={win.link} onChange={(c: LinkColor) => updateWindow(win.id, { link: c })} />}
        <div className={locked ? 'wf-drag locked' : 'wf-drag'} title={locked ? 'Layout locked' : 'Drag to move · double-click to maximize'}>
          <span className="faint" style={{ fontSize: 11 }}>{WINDOW_ICONS[win.type]}</span>
          {renaming != null ? (
            <input className="wf-title-input wf-nodrag" autoFocus value={renaming} placeholder={WINDOW_TITLES[win.type]}
              onChange={e => setRenaming(e.target.value)} onFocus={e => e.currentTarget.select()}
              onPointerDown={e => e.stopPropagation()} onDoubleClick={e => e.stopPropagation()}
              onBlur={commitTitle}
              onKeyDown={e => { if (e.key === 'Enter') commitTitle(); if (e.key === 'Escape') { e.stopPropagation(); setRenaming(null) } }} />
          ) : (
            <span className="wf-title renamable wf-nodrag" title="Click to rename"
              onDoubleClick={e => e.stopPropagation()} onClick={() => setRenaming(title)}>{title}</span>
          )}
          {sub && <span className={`wf-sub${linkedSymbol && sub.text === linkedSymbol ? ' linked' : sub.strong ? ' strong' : ''}`} title={linkedSymbol && sub.text === linkedSymbol ? `Link group ${win.link}: ${linkedSymbol}` : undefined}>{sub.text}</span>}
        </div>
        {USES_SOUND[win.type] && (
          <button className={`wf-ctl wf-nodrag${win.muted ? '' : ' on'}`} title={win.muted ? 'Unmute window' : 'Mute window'}
            onClick={() => updateWindow(win.id, { muted: !win.muted })}>{win.muted ? '🔇' : '🔔'}</button>
        )}
        {Settings && (
          <button className={`wf-ctl wf-nodrag${settingsAt ? ' on' : ''}`} title="Settings"
            onClick={e => { const r = e.currentTarget.getBoundingClientRect(); setSettingsAt(a => (a ? null : r)) }}>⚙</button>
        )}
        {!locked && onToggleMaximize && (
          <button className={`wf-ctl wf-nodrag${maximized ? ' on' : ''}`} title={maximized ? 'Restore size' : 'Maximize'} onClick={onToggleMaximize}>{maximized ? '❐' : '▢'}</button>
        )}
        {!locked && (
          <button className="wf-ctl wf-nodrag close" title="Close window" onClick={() => removeWindow(win.id)}>✕</button>
        )}
      </div>
      <div className="wf-body wf-nodrag">
        <WindowErrorBoundary name={title}>
          <Body win={win as never} />
        </WindowErrorBoundary>
      </div>
      {settingsAt && Settings && (
        <SettingsPopup title={title} anchor={settingsAt} onClose={() => setSettingsAt(null)}>
          <div className="wf-settings">
            <Field label="Window title">
              <input className="input sm" value={win.title ?? ''} placeholder={WINDOW_TITLES[win.type]} onChange={e => updateWindow(win.id, { title: e.target.value || undefined })} />
            </Field>
            <Settings win={win as never} onChange={(patch: Record<string, unknown>) => updateWindow(win.id, patch)} />
          </div>
        </SettingsPopup>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div className="field"><label>{label}</label>{children}</div>
}
