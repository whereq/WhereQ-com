import { useEffect, useRef, useState } from 'react'
import { useMapsLibrary } from '@vis.gl/react-google-maps'
import { api } from '@/lib/api'
import { placeLabel } from '@/lib/searchColors'
import { useAuth } from '@/contexts/AuthContext'
import type { PlaceDTO } from '@/hooks/usePlaces'

export interface SearchResult {
  id: string
  name: string
  meta: string
  kind: string            // address | school | poi | pharmacy | clinic | ...
  category?: string       // POI category (food, coffee, gas, ...) when known
  lat?: number
  lng?: number
  gPlaceId?: string       // unresolved Google prediction
  /** The Google prediction itself — it knows its place, so it can be resolved
   *  with the modern Places API instead of a separate geocode call. */
  placePrediction?: google.maps.places.PlacePrediction
}

interface SchoolsResp { items: { id: number; name: string; lat: number | null; lng: number | null; city?: string | null }[] }

/** A resolved place: where it is, and (when Google knows it) its address. */
export interface ResolvedPlace {
  lat: number
  lng: number
  /** The full address, e.g. "222 Woodbridge Ave, Vaughan, ON L4L 2S8, Canada". */
  address?: string
}

/** One Google Places prediction, normalised for the result list. */
interface AddressPrediction {
  placeId: string
  main: string
  secondary: string
  prediction: google.maps.places.PlacePrediction
}

/**
 * Google Places Autocomplete — the modern API.
 *
 * `google.maps.places.AutocompleteService` is deprecated: as of March 1st,
 * 2025 it is closed to new customers and Google logs a deprecation warning
 * for it. `AutocompleteSuggestion.fetchAutocompleteSuggestions` replaces it;
 * it returns the same place id (which is what the place id is for), so
 * nothing else in the app has to change.
 */
async function getPredictions(
  placesLib: google.maps.PlacesLibrary | null,
  input: string,
  sessionToken: google.maps.places.AutocompleteSessionToken | null,
): Promise<AddressPrediction[]> {
  if (!placesLib?.AutocompleteSuggestion) return []
  try {
    const { suggestions } = await placesLib.AutocompleteSuggestion.fetchAutocompleteSuggestions({
      input,
      includedRegionCodes: ['ca'],
      ...(sessionToken ? { sessionToken } : {}),
    })
    return suggestions
      .map(s => s.placePrediction)
      .filter((p): p is google.maps.places.PlacePrediction => !!p)
      .slice(0, 6)
      .map(p => ({
        placeId: p.placeId,
        main: p.mainText?.text ?? p.text.text,
        secondary: p.secondaryText?.text ?? '',
        prediction: p,
      }))
  } catch {
    // A failed prediction call must not break the rest of the search.
    return []
  }
}

/**
 * Unified "Where to?" search: our schools + POIs (with coordinates) plus Google
 * Places Autocomplete for streets/addresses/places. Google predictions resolve
 * to coordinates lazily via `resolve()` on selection.
 *
 * `enabled` turns the lookup off without unmounting the hook — the nearby tab
 * uses this so it does not fire a text search behind the nearby list.
 */
export function useSearch(query: string, debounceMs = 280, enabled = true) {
  const { isAuthenticated } = useAuth()
  const placesLib = useMapsLibrary('places')
  const geocodingLib = useMapsLibrary('geocoding')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()
  // Monotonic request id — a slow response from an older query must never
  // overwrite the results of a newer one (R35).
  const seq = useRef(0)
  // One autocomplete session per search: a fresh token starts with the first
  // keystroke, so the whole typing sequence is billed as one session instead
  // of one request per keystroke. It ends when the box is cleared or the
  // search is left.
  const session = useRef<google.maps.places.AutocompleteSessionToken | null>(null)

  useEffect(() => {
    clearTimeout(timer.current)
    const q = query.trim()
    // Invalidate whatever is in flight: the query changed, so its answer is
    // stale no matter when it arrives.
    const mySeq = ++seq.current
    if (!q || !enabled) {
      // The session is over — an empty box or a closed search ends it.
      session.current = null
      setResults([]); setLoading(false); return
    }
    setLoading(true)

    timer.current = setTimeout(async () => {
      // Start a session for this search if there is none.
      if (!session.current && placesLib?.AutocompleteSessionToken) {
        try {
          session.current = new placesLib.AutocompleteSessionToken()
        } catch { /* no session token — every request is billed on its own */ }
      }

      // Google Places Autocomplete is billable → signed-in users only. Our own
      // DB (schools + POIs) is free and stays available to everyone.
      const [places, schools, preds] = await Promise.all([
        api.get<PlaceDTO[]>(`/places?search=${encodeURIComponent(q)}&limit=6`).catch(() => [] as PlaceDTO[]),
        api.get<SchoolsResp>(`/schools?q=${encodeURIComponent(q)}&page_size=5`).catch(() => ({ items: [] as SchoolsResp['items'] })),
        isAuthenticated ? getPredictions(placesLib, q, session.current) : Promise.resolve([] as AddressPrediction[]),
      ])

      // A newer query has been issued in the meantime — drop this answer.
      if (mySeq !== seq.current) return

      const out: SearchResult[] = []
      for (const s of schools.items) {
        if (s.lat != null && s.lng != null)
          out.push({ id: `school-${s.id}`, name: s.name, meta: `School${s.city ? ` · ${s.city}` : ''}`, kind: 'school', lat: s.lat, lng: s.lng })
      }
      for (const p of places)
        out.push({
          id: `place-${p.id}`,
          name: p.name,
          meta: `${placeLabel(p)}${p.city ? ` · ${p.city}` : ''}`,
          kind: p.kind,
          category: p.category || undefined,
          lat: p.latitude,
          lng: p.longitude,
        })
      for (const pr of preds)
        out.push({
          id: `g-${pr.placeId}`,
          name: pr.main,
          meta: pr.secondary || 'Address',
          kind: 'address',
          gPlaceId: pr.placeId,
          placePrediction: pr.prediction,
        })

      setResults(out)
      setLoading(false)
    }, debounceMs)

    return () => clearTimeout(timer.current)
  }, [query, debounceMs, placesLib, isAuthenticated, enabled])

  /**
   * Resolve a result to coordinates.
   *
   * A Google prediction knows its place: `toPlace()` + `fetchFields` gives
   * the location (and ends the autocomplete session, so the whole search is
   * billed as one session). The Geocoding API by place id stays as the
   * fallback for a prediction we no longer hold in memory.
   */
  const resolve = async (r: SearchResult): Promise<ResolvedPlace | null> => {
    if (r.lat != null && r.lng != null) return { lat: r.lat, lng: r.lng }
    if (!isAuthenticated) return null

    if (r.placePrediction) {
      try {
        const place = r.placePrediction.toPlace()
        await place.fetchFields({ fields: ['location', 'formattedAddress'] })
        const loc = place.location
        if (loc) {
          return {
            lat: loc.lat(),
            lng: loc.lng(),
            address: place.formattedAddress ?? undefined,
          }
        }
      } catch {
        // Fall through to the geocoder below.
      }
    }

    if (!r.gPlaceId || !geocodingLib) return null
    return new Promise((res) => {
      new geocodingLib.Geocoder().geocode({ placeId: r.gPlaceId! }, (g, status) => {
        if (status === 'OK' && g?.[0]) {
          const loc = g[0].geometry.location
          res({
            lat: loc.lat(),
            lng: loc.lng(),
            address: g[0].formatted_address ?? undefined,
          })
        } else res(null)
      })
    })
  }

  return { results, loading, resolve, addressSearchGated: !isAuthenticated }
}
