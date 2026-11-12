import { useEffect, useState, useRef, useCallback } from 'react'
import { getToken } from '@/lib/auth'

export interface FriendLocation {
  user_id: number
  username: string
  lat: number
  lng: number
}

/** Close code the API uses when the token is missing or invalid. */
const UNAUTHORIZED_CLOSE = 4001

/** Reconnect backoff bounds (ms). */
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

/**
 * Build the WebSocket endpoint for the location channel.
 *
 * In production the SPA is served from the same origin as the API (nginx
 * proxies `/api` to the API container), so the socket must use the page's
 * host. Deriving the host from `VITE_API_URL` alone breaks there: in
 * production that variable is the relative "/api", which yields an empty host
 * and falls back to "localhost:8000" — the visitor's own machine, which is
 * why friend presence was dead in production.
 *
 * An absolute API base (the local dev setup) is still honoured, so the
 * socket talks straight to the API when it is not same-origin.
 */
function wsEndpoint(token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const apiUrl = (import.meta.env.VITE_API_URL ?? '').trim()
  const host = /^https?:\/\//i.test(apiUrl)
    ? apiUrl.replace(/^https?:\/\//i, '').replace(/\/api\/?$/, '')
    : window.location.host
  return `${protocol}://${host}/api/ws/location?token=${encodeURIComponent(token)}`
}

export function useFriendsNearby() {
  const [friends, setFriends] = useState<FriendLocation[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const stoppedRef = useRef(false)
  const connectRef = useRef<() => void>(() => {})

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const scheduleReconnect = useCallback(() => {
    if (stoppedRef.current) return
    clearTimer()
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS)
    attemptRef.current += 1
    timerRef.current = setTimeout(() => connectRef.current(), delay)
  }, [clearTimer])

  const connect = useCallback(() => {
    stoppedRef.current = false
    const token = getToken()
    if (!token) return

    let ws: WebSocket
    try {
      ws = new WebSocket(wsEndpoint(token))
    } catch {
      scheduleReconnect()
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      attemptRef.current = 0
      setConnected(true)
    }

    ws.onclose = (ev) => {
      setConnected(false)
      // An invalid token will not fix itself — retrying would just spin.
      if (ev.code === UNAUTHORIZED_CLOSE) {
        stoppedRef.current = true
        return
      }
      scheduleReconnect()
    }

    ws.onerror = () => {
      // The close handler drives the retry; swallow the error event so it
      // does not surface as an unhandled error in the console.
    }

    ws.onmessage = (e) => {
      let msg: { type?: string; user_id?: number; username?: string; lat?: number; lng?: number }
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }
      if (msg?.type !== 'friend_location' || typeof msg.user_id !== 'number') return
      setFriends(prev => {
        const idx = prev.findIndex(f => f.user_id === msg.user_id)
        const updated: FriendLocation = {
          user_id: msg.user_id!,
          username: msg.username ?? '',
          lat: msg.lat ?? 0,
          lng: msg.lng ?? 0,
        }
        if (idx >= 0) {
          const next = [...prev]
          next[idx] = updated
          return next
        }
        return [...prev, updated]
      })
    }
  }, [scheduleReconnect])

  // Keep the latest `connect` reachable from the reconnect timer without
  // making the timer depend on it (which would restart it every render).
  useEffect(() => { connectRef.current = connect }, [connect])

  const disconnect = useCallback(() => {
    stoppedRef.current = true
    clearTimer()
    wsRef.current?.close()
    wsRef.current = null
    setConnected(false)
  }, [clearTimer])

  const sendLocation = useCallback((lat: number, lng: number, username: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'location', lat, lng, username }))
    }
  }, [])

  useEffect(() => {
    return () => {
      stoppedRef.current = true
      clearTimer()
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [clearTimer])

  return { friends, connected, connect, disconnect, sendLocation }
}
