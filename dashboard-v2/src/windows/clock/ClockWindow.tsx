import { useEffect, useState } from 'react'
import type { ClockConfig } from '../../types'
import { api } from '../../lib/api'
import { usePoll } from '../../lib/usePoll'
import { fmtCountdown, nowET } from '../../lib/time'
import { fmtPct, fmtPrice } from '../../lib/format'
import { useFeeds, visibleSources, SOURCE_LABEL, SOURCE_SHORT } from '../../stores/feedsStore'
import { useCapabilities } from '../../stores/capabilitiesStore'
import { Toggle } from '../../components/primitives'

const SESSION_LABEL = { pre: 'PRE-MARKET', rth: 'MARKET OPEN', post: 'AFTER HOURS', closed: 'CLOSED' } as const

export function ClockWindow({ win }: { win: ClockConfig }) {
  const [clock, setClock] = useState(nowET)
  const [tick, setTick] = useState(() => Date.now())
  const { data } = usePoll(api.clock, 2000)
  const status = useFeeds(s => s.status)
  const counts = useFeeds(s => s.counts)
  const hasSystem = useCapabilities(s => s.system_setups)
  useEffect(() => { const t = setInterval(() => { setClock(nowET()); setTick(Date.now()) }, 1000); return () => clearInterval(t) }, [])

  const session = data?.session ?? 'closed'
  const replay = data?.replay ?? null
  const cursor = replay?.cursor_et ? new Date(replay.cursor_et).getTime() : null
  const next = data?.next_change_et ? new Date(data.next_change_et).getTime() - (cursor ?? tick) : null
  const regime = (data?.regime ?? 'neutral').toLowerCase()
  const spy = data?.spy
  const shown = replay?.cursor_et
    ? new Date(replay.cursor_et).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false })
    : clock

  return (
    <div className="clockbar">
      <span className="big">{shown}<span className="clock-tz" style={{ fontSize: 11 }}>ET</span></span>
      {replay && <span className="sess" style={{ color: 'var(--link-purple)', borderColor: 'var(--link-purple)' }} title={`Replaying ${replay.date} at ${replay.speed}x`}>REPLAY {replay.date} · {replay.speed}x</span>}
      <span className={`sess ${session}`}>{SESSION_LABEL[session]}</span>
      {next != null && next > 0 && (
        <span className="stat"><span className="lbl">{session === 'rth' ? 'closes in' : session === 'closed' ? 'pre-market in' : 'next in'}</span><span className="val">{fmtCountdown(next)}</span></span>
      )}
      <span className={`regime ${regime}`}><span className="dot" style={{ background: 'currentColor' }} />{regime}</span>
      {win.showSpy && spy && (
        <span className="stat"><span className="lbl">SPY</span>
          <span className="val">{fmtPrice(spy.price)} <span className={spy.chg_pct != null ? (spy.chg_pct > 0 ? 'up' : spy.chg_pct < 0 ? 'down' : '') : ''}>{fmtPct(spy.chg_pct)}</span>
            {spy.vwap != null && spy.price != null && <span className="faint" style={{ fontSize: 10.5 }}> {spy.price >= spy.vwap ? '▲' : '▼'} VWAP {fmtPrice(spy.vwap)}</span>}
          </span>
        </span>
      )}
      <span className="flex-spacer" />
      <span className="row" style={{ gap: 10 }}>
        <span className="row" style={{ gap: 4, fontSize: 10.5 }} title={`Alert feed: ${status}`}>
          <span className={`dot ${status === 'connected' ? 'ok' : status === 'reconnecting' ? 'warn' : 'bad'}`} /><span className="faint">Feed</span>
        </span>
        {visibleSources(hasSystem).map(f => <span key={f} className="faint mono" style={{ fontSize: 10.5 }} title={`${SOURCE_LABEL[f]} alerts today`}>{SOURCE_SHORT[f]} {counts[f]}</span>)}
      </span>
    </div>
  )
}

export function ClockSettings({ win, onChange }: { win: ClockConfig; onChange(p: Partial<ClockConfig>): void }) {
  return <Toggle checked={win.showSpy} onChange={showSpy => onChange({ showSpy })} label="Show SPY price / VWAP" />
}
