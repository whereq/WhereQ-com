import { useState, useRef, useCallback } from 'react'
import { api } from '@/lib/api'

interface Waypoint {
  lat: number
  lng: number
  timestamp: string
}

interface TrackedRoute {
  id: number | null
  name: string
  waypoints: Waypoint[]
  startTime: number
  distance: number // km
}

function haversineKm(a: Waypoint, b: Waypoint): number {
  const R = 6371
  const dLat = (b.lat - a.lat) * Math.PI / 180
  const dLng = (b.lng - a.lng) * Math.PI / 180
  const x =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) *
    Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x))
}

export function useRouteTracker() {
  const [tracking, setTracking] = useState(false)
  const [route, setRoute] = useState<TrackedRoute | null>(null)
  const watchId = useRef<number | null>(null)
  const routeRef = useRef<TrackedRoute | null>(null)

  const startTracking = useCallback(async (name: string) => {
    if (!navigator.geolocation) return

    // Create route on backend
    let routeId: number | null = null
    try {
      const created = await api.post<{ id: number }>('/routes', { name, waypoints: [] })
      routeId = created.id
    } catch {
      // continue tracking locally even if backend fails
    }

    const newRoute: TrackedRoute = {
      id: routeId,
      name,
      waypoints: [],
      startTime: Date.now(),
      distance: 0,
    }
    routeRef.current = newRoute
    setRoute(newRoute)
    setTracking(true)

    watchId.current = navigator.geolocation.watchPosition(
      (pos) => {
        const wp: Waypoint = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          timestamp: new Date().toISOString(),
        }

        const cur = routeRef.current
        if (!cur) return

        let addedDist = 0
        if (cur.waypoints.length > 0) {
          addedDist = haversineKm(cur.waypoints[cur.waypoints.length - 1], wp)
        }

        const updated: TrackedRoute = {
          ...cur,
          waypoints: [...cur.waypoints, wp],
          distance: cur.distance + addedDist,
        }
        routeRef.current = updated
        setRoute({ ...updated })
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 5000 },
    )
  }, [])

  const stopTracking = useCallback(async () => {
    if (watchId.current !== null) {
      navigator.geolocation.clearWatch(watchId.current)
      watchId.current = null
    }
    setTracking(false)

    const cur = routeRef.current
    if (cur?.id && cur.waypoints.length > 0) {
      try {
        await api.post(`/routes/${cur.id}/waypoints`, cur.waypoints)
      } catch {
        // waypoints saved locally only
      }
    }
  }, [])

  const elapsed = route ? Math.floor((Date.now() - route.startTime) / 60000) : 0

  return { tracking, route, elapsed, startTracking, stopTracking }
}
