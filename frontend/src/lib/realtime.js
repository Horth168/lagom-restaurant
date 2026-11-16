// Live updates from the backend over a WebSocket, with automatic reconnect.
// Messages only say "something changed"; screens then reload through the normal API.
import { useEffect, useRef, useState } from 'react'

function socketUrl(path) {
  const base = import.meta.env.VITE_API_URL || window.location.origin
  return base.replace(/^http/, 'ws').replace(/\/$/, '') + path
}

/**
 * useLiveChannel('/api/ws/staff', { token, station }, onMessage)
 * Returns 'connecting' | 'live' | 'offline'.
 */
export function useLiveChannel(path, hello, onMessage, enabled = true) {
  const [state, setState] = useState('connecting')
  const handler = useRef(onMessage)
  useEffect(() => {
    handler.current = onMessage
  })
  const helloKey = JSON.stringify(hello)

  useEffect(() => {
    if (!enabled) return
    let ws
    let stopped = false
    let attempt = 0
    let retryTimer
    let pingTimer

    const connect = () => {
      setState('connecting')
      ws = new WebSocket(socketUrl(path))
      ws.onopen = () => ws.send(helloKey)
      ws.onmessage = (e) => {
        let msg
        try {
          msg = JSON.parse(e.data)
        } catch {
          return
        }
        if (msg.type === 'ready') {
          attempt = 0
          setState('live')
          handler.current?.({ type: 'reconnected' }) // reload once, in case something was missed
          return
        }
        if (msg.type !== 'pong') handler.current?.(msg)
      }
      ws.onclose = (e) => {
        clearInterval(pingTimer)
        if (stopped) return
        setState('offline')
        if (e.code === 4401 || e.code === 4403) return // not allowed: do not hammer the server
        const delay = Math.min(30000, 1000 * 2 ** attempt++) // 1s, 2s, 4s … max 30s
        retryTimer = setTimeout(connect, delay)
      }
      pingTimer = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send('ping'), 25000)
    }
    connect()
    return () => {
      stopped = true
      clearTimeout(retryTimer)
      clearInterval(pingTimer)
      ws?.close()
    }
  }, [path, helloKey, enabled])

  return state
}
