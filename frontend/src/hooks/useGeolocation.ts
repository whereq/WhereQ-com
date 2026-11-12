import { useEffect, useState, useCallback } from 'react'

interface GeoPosition {
  lat: number
  lng: number
  accuracy: number
}

export function useGeolocation() {
  const [position, setPosition] = useState<GeoPosition | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [watching, setWatching] = useState(false)

  const startWatching = useCallback(() => {
    if (!navigator.geolocation) {
      setError('Geolocation not supported')
      return
    }
    setWatching(true)
  }, [])

  const stopWatching = useCallback(() => {
    setWatching(false)
  }, [])

  useEffect(() => {
    if (!watching || !navigator.geolocation) return

    const id = navigator.geolocation.watchPosition(
      (pos) => {
        setPosition({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        })
        setError(null)
      },
      (err) => {
        setError(err.message)
      },
      { enableHighAccuracy: true, maximumAge: 10000 }
    )

    return () => navigator.geolocation.clearWatch(id)
  }, [watching])

  return { position, error, watching, startWatching, stopWatching }
}
