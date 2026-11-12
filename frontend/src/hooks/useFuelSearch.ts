import { useEffect, useState } from 'react'
import { fuelApi } from '@/lib/fuelApi'
import { ApiError } from '@/lib/api'
import { reportError } from '@/lib/errorBus'

export interface FuelSearchResult {
  id: string
  name: string
  /** "1.67 CAD/L · 2.1 km · Vaughan" */
  meta: string
  kind: 'gas'
  lat: number
  lng: number
  price: number | null
  currency: string | null
}

interface Options {
  query: string
  enabled: boolean
  /** Where "nearby" is measured from — the map centre. */
  center: { lat: number; lng: number } | null
  /** Fallback filter when the map hasn't reported a centre yet. */
  bbox?: string | null
  sort: 'distance' | 'price'
  radiusKm?: number
}

/**
 * Gas stations near the map centre, with their prices.
 *
 * Reads our own /api/fuel/stations (already crawled from whereq.cloud), so
 * the search is free and the whereq.cloud key never reaches the browser.
 */
export function useFuelSearch({ query, enabled, center, bbox, sort, radiusKm = 25 }: Options) {
  const [results, setResults] = useState<FuelSearchResult[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!enabled) {
      setResults([])
      return
    }
    let cancelled = false
    setLoading(true)

    fuelApi.stations({
      q: query.trim() || undefined,
      lat: center?.lat,
      lng: center?.lng,
      radiusKm: center ? radiusKm : undefined,
      // Without a centre, fall back to whatever the map is showing.
      bbox: center ? undefined : (bbox ?? undefined),
      sort,
      limit: 8,
    })
      .then((stations) => {
        if (cancelled) return
        setResults(stations.map((s) => {
          const price = s.price != null
            ? `${s.price.toFixed(2)} ${s.currency ?? ''}/L`.trim()
            : null
          const bits = [price, s.distance_km != null ? `${s.distance_km} km` : null, s.city]
            .filter(Boolean)
          return {
            id: `gas-${s.id}`,
            name: s.brand || s.name,
            meta: bits.join(' · '),
            kind: 'gas' as const,
            lat: s.lat,
            lng: s.lng,
            price: s.price,
            currency: s.currency,
          }
        }))
      })
      .catch((err) => {
        if (cancelled) return
        setResults([])
        // A 401 here means the caller is not signed in — the prices are
        // licensed. Say that, instead of showing an empty "no results" list.
        if (err instanceof ApiError && err.status === 401) {
          reportError('signin', { code: 'toast.signInForPrices' })
        }
      })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [query, enabled, center?.lat, center?.lng, bbox, sort, radiusKm])

  return { results, loading }
}
