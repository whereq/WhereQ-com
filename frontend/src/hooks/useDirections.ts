import { useState, useCallback } from 'react'
import { useMap, useMapsLibrary } from '@vis.gl/react-google-maps'

export interface DirectionsResult {
  routes: google.maps.DirectionsRoute[]
  duration: string
  distance: string
}

export function useDirections() {
  const map = useMap()
  const routesLib = useMapsLibrary('routes')
  const [result, setResult] = useState<DirectionsResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [renderer, setRenderer] = useState<google.maps.DirectionsRenderer | null>(null)

  const getDirections = useCallback(
    async (
      origin: google.maps.LatLngLiteral,
      destination: google.maps.LatLngLiteral,
      travelMode: google.maps.TravelMode = google.maps.TravelMode.DRIVING,
      waypoints: google.maps.LatLngLiteral[] = [],
    ) => {
      if (!routesLib || !map) {
        setError('Maps not ready')
        return
      }

      // Clear previous
      renderer?.setMap(null)

      setLoading(true)
      setError(null)

      const service = new routesLib.DirectionsService()
      const newRenderer = new routesLib.DirectionsRenderer({
        map,
        suppressMarkers: true,
        polylineOptions: {
          strokeColor: '#60A5FA',
          strokeWeight: 5,
          strokeOpacity: 0.8,
        },
      })
      setRenderer(newRenderer)

      try {
        const response = await service.route({
          origin,
          destination,
          travelMode,
          waypoints: waypoints.map((location) => ({ location, stopover: true })),
        })

        newRenderer.setDirections(response)

        // Sum across all legs (multi-stop routes).
        const legs = response.routes[0]?.legs ?? []
        const meters = legs.reduce((s, l) => s + (l.distance?.value ?? 0), 0)
        const seconds = legs.reduce((s, l) => s + (l.duration?.value ?? 0), 0)
        const km = meters / 1000
        const mins = Math.round(seconds / 60)
        const dur = mins >= 60 ? `${Math.floor(mins / 60)} h ${mins % 60} min` : `${mins} min`
        setResult({
          routes: response.routes,
          duration: dur,
          distance: km >= 10 ? `${Math.round(km)} km` : `${km.toFixed(1)} km`,
        })
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Directions failed')
        newRenderer.setMap(null)
      } finally {
        setLoading(false)
      }
    },
    [map, routesLib, renderer],
  )

  const clearDirections = useCallback(() => {
    renderer?.setMap(null)
    setRenderer(null)
    setResult(null)
    setError(null)
  }, [renderer])

  return { result, loading, error, getDirections, clearDirections }
}
