import { createContext, useContext, useState, ReactNode } from 'react'

export type TravelMode = 'DRIVING' | 'WALKING' | 'BICYCLING' | 'TRANSIT'

export interface RouteStop { lat: number; lng: number; label?: string }
export interface RouteResult { distance: string; duration: string }

interface RouteContextValue {
  /** Ordered destinations after the current location (last = final destination,
   *  earlier = waypoints). */
  stops: RouteStop[]
  travelMode: TravelMode
  result: RouteResult | null
  active: boolean
  /** Replace the route with a single destination. */
  routeTo: (s: RouteStop) => void
  /** Append a stop (waypoint / new final destination). */
  addStop: (s: RouteStop) => void
  removeStop: (i: number) => void
  clear: () => void
  setTravelMode: (m: TravelMode) => void
  /** Written by the map executor once a route is computed. */
  setResult: (r: RouteResult | null) => void
}

const RouteContext = createContext<RouteContextValue | null>(null)

export function RouteProvider({ children }: { children: ReactNode }) {
  const [stops, setStops] = useState<RouteStop[]>([])
  const [travelMode, setTravelMode] = useState<TravelMode>('DRIVING')
  const [result, setResult] = useState<RouteResult | null>(null)

  const routeTo = (s: RouteStop) => setStops([s])
  const addStop = (s: RouteStop) => setStops((prev) => [...prev, s])
  const removeStop = (i: number) => setStops((prev) => prev.filter((_, idx) => idx !== i))
  const clear = () => { setStops([]); setResult(null) }

  return (
    <RouteContext.Provider value={{
      stops, travelMode, result, active: stops.length > 0,
      routeTo, addStop, removeStop, clear, setTravelMode, setResult,
    }}>
      {children}
    </RouteContext.Provider>
  )
}

export function useRouteContext() {
  const ctx = useContext(RouteContext)
  if (!ctx) throw new Error('useRouteContext must be used within RouteProvider')
  return ctx
}
