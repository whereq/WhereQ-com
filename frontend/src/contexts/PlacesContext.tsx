import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from 'react'
import { usePlaces, PlaceDTO } from '@/hooks/usePlaces'
import { useNeighborhoodInsights, NeighborhoodInfo } from '@/hooks/useNeighborhoodInsights'
import { useMapContext } from '@/contexts/MapContext'
import { placesApi } from '@/lib/placesApi'
import { schoolsMapApi } from '@/lib/schoolsMapApi'
import type { MapPin } from '@/types/map'
import type { PlaceCounts } from '@/types/place'
import { PINS as FALLBACK_PINS } from '@/components/map/mapData'

interface PlacesContextValue {
  places: PlaceDTO[]
  pins: MapPin[]
  neighborhood: NeighborhoodInfo | null
  loading: boolean
  error: string | null
  /** Counts by kind for sidebar essentials */
  counts: Record<string, number>
}

const PlacesContext = createContext<PlacesContextValue | null>(null)

/** Convert a PlaceDTO to a MapPin for rendering on the map */
function placeToPin(p: PlaceDTO): MapPin {
  const meta = p.metadata_json ?? {}
  return {
    id: `place-${p.id}`,
    x: 0,
    y: 0,
    lat: p.latitude,
    lng: p.longitude,
    kind: p.kind as MapPin['kind'],
    title: p.name,
    sub: p.sub ?? undefined,
    story: p.description ?? undefined,
    cat: p.kind === 'poi' ? (p.category as MapPin['cat']) : undefined,
    level: (meta.level as MapPin['level']) ?? undefined,
    grade: (meta.grade as string) ?? undefined,
  }
}

export function PlacesProvider({ children }: { children: ReactNode }) {
  const { places, loading: placesLoading, error: placesError } = usePlaces()
  const { mapBbox, mapCenter } = useMapContext()
  const neighborhood = useNeighborhoodInsights(mapCenter)

  const loading = placesLoading
  const error = placesError

  // Convert API places to MapPins; fall back to hardcoded pins if API fails or returns empty
  const pins = useMemo(() => {
    if (places.length === 0 && !loading) return FALLBACK_PINS
    if (places.length === 0) return []
    return places.map(placeToPin)
  }, [places, loading])

  // Counts for the sidebar (essentials + quick categories) are viewport-scoped:
  // they track what's actually visible on the map via /places/counts.
  const [counts, setCounts] = useState<PlaceCounts>({})
  useEffect(() => {
    if (!mapBbox) return
    let cancelled = false
    // POI counts (places) + schools count (separate tables) for the viewport.
    Promise.allSettled([placesApi.counts(mapBbox), schoolsMapApi.count(mapBbox)])
      .then(([poi, school]) => {
        if (cancelled) return
        const next: PlaceCounts = poi.status === 'fulfilled' ? { ...poi.value } : {}
        if (school.status === 'fulfilled') next.school = school.value
        setCounts(next)
      })
    return () => { cancelled = true }
  }, [mapBbox])

  return (
    <PlacesContext.Provider value={{ places, pins, neighborhood, loading, error, counts }}>
      {children}
    </PlacesContext.Provider>
  )
}

export function usePlacesContext() {
  const ctx = useContext(PlacesContext)
  if (!ctx) throw new Error('usePlacesContext must be used within PlacesProvider')
  return ctx
}
