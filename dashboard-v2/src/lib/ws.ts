import type { Alert, ConnectionStatus } from '../types'

const INITIAL_BACKOFF = 1000
const MAX_BACKOFF = 30000

export interface AlertSocket { close(): void }

/** One reconnecting WebSocket to a scanner alert feed. The server sends
 *  {type:"replay", alerts:[...]} on connect, then {type:"alert", alert:{...}}. */
export function openAlertSocket(
  url: string,
  handlers: {
    onReplay(alerts: Alert[]): void
    onAlert(alert: Alert): void
    onStatus(s: ConnectionStatus): void
  },
): AlertSocket {
  let ws: WebSocket | null = null
  let backoff = INITIAL_BACKOFF
  let timer: ReturnType<typeof setTimeout> | null = null
  let closed = false

  const connect = () => {
    if (closed) return
    handlers.onStatus('reconnecting')
    ws = new WebSocket(url)
    ws.onopen = () => { backoff = INITIAL_BACKOFF; handlers.onStatus('connected') }
    ws.onmessage = evt => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === 'alert' && msg.alert) handlers.onAlert(msg.alert)
        else if (msg.type === 'replay') handlers.onReplay(msg.alerts ?? [])
      } catch { /* ignore malformed frame */ }
    }
    ws.onclose = () => {
      if (closed) return
      handlers.onStatus('disconnected')
      timer = setTimeout(() => { backoff = Math.min(backoff * 2, MAX_BACKOFF); connect() }, backoff)
    }
    ws.onerror = () => { ws?.close() }
  }
  connect()
  return {
    close() { closed = true; if (timer) clearTimeout(timer); ws?.close() },
  }
}
