import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'

export interface NeighborhoodInfo {
  name: string
  city: string
  country: string
  /** 0–100 scores computed from our own POI data. */
  walk: number
  transit: number
  bike: number
  greenery: number
}

interface LatLng { lat: number; lng: number }

function metersBetween(a: LatLng, b: LatLng): number {
  const R = 6371000
  const dLat = (b.lat - a.lat) * Math.PI / 180
  const dLng = (b.lng - a.lng) * Math.PI / 180
  const la1 = a.lat * Math.PI / 180, la2 = b.lat * Math.PI / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

/** Reverse-geocode a point to { name, city, country } using the Google geocoder
 *  (the map already loads the Maps JS API). Resolves to blanks on any failure. */
function reverseGeocode(p: LatLng): Promise<{ name: string; city: string; country: string }> {
  return new Promise((resolve) => {
    const g = (window as any).google?.maps?.Geocoder
    if (!g) { resolve({ name: '', city: '', country: '' }); return }
    new g().geocode({ location: p }, (results: any[], status: string) => {
      if (status !== 'OK' || !results?.length) { resolve({ name: '', city: '', country: '' }); return }
      let name = '', city = '', country = ''
      for (const r of results) {
        for (const c of r.address_components ?? []) {
          const ty: string[] = c.types ?? []
          if (!name && (ty.includes('neighborhood') || ty.includes('sublocality') || ty.includes('sublocality_level_1')))
            name = c.long_name
          if (!city && (ty.includes('locality') || ty.includes('postal_town') || ty.includes('administrative_area_level_2')))
            city = c.long_name
          if (!country && ty.includes('country')) country = c.short_name
        }
      }
      if (!name) name = city || (results[0].formatted_address?.split(',')[0] ?? '')
      resolve({ name, city, country })
    })
  })
}

/**
 * Detect the neighborhood/city for a map center and fetch its computed
 * Walk/Transit/Bike/Greenery scores. Recomputes only after a significant move
 * (~300 m) to avoid spamming the geocoder / API on small pans.
 */
export function useNeighborhoodInsights(center: LatLng | null): NeighborhoodInfo | null {
  const { isAuthenticated } = useAuth()
  const [info, setInfo] = useState<NeighborhoodInfo | null>(null)
  const last = useRef<LatLng | null>(null)

  useEffect(() => {
    if (!center) return
    if (last.current && metersBetween(last.current, center) < 300) return
    last.current = center
    let cancelled = false

    Promise.all([
      // Reverse geocoding is billable → signed-in only. Scores come from our DB.
      isAuthenticated ? reverseGeocode(center) : Promise.resolve({ name: '', city: '', country: '' }),
      api.get<{ walk: number; transit: number; bike: number; greenery: number }>(
        `/neighborhoods/insights?lat=${center.lat}&lng=${center.lng}`,
      ).catch(() => null),
    ]).then(([geo, scores]) => {
      if (cancelled) return
      setInfo({
        // Empty when the name is unknown (an anonymous visitor skips the
        // billable reverse geocode). An empty string lets the UI fall back to
        // its locale default — a stale city name is worse than no name.
        name: geo.name,
        city: geo.city,
        country: geo.country,
        walk: scores?.walk ?? 0,
        transit: scores?.transit ?? 0,
        bike: scores?.bike ?? 0,
        greenery: scores?.greenery ?? 0,
      })
    })

    return () => { cancelled = true }
  }, [center?.lat, center?.lng, isAuthenticated])  // eslint-disable-line react-hooks/exhaustive-deps

  return info
}
