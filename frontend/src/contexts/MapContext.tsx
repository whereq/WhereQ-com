import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react'
import type { MapFilters, MapEssentials, MapStyle, LogoVariant } from '@/types/map'
import type { MapSelection } from '@/types/selection'
import type { GeoGeometry } from '@/types/geo'

/** A "pan the map here" request. `nonce` makes a repeat of the same place a
 *  new request (the map would otherwise ignore an identical target). */
export interface MapFocusRequest {
  lat: number
  lng: number
  name?: string
  nonce: number
}

/** What the search modal is showing. */
export type SearchMode =
  | 'all'        // the text search
  | 'gas'        // the gas stations
  | 'nearby'     // everything around the map centre
  | 'place'      // the picked place + what is around it
  | 'stop'       // pick a place to add as a route stop

/**
 * "Draw this administrative area on the map."
 *
 * The card of a place answers "contained in" with a stack of areas — a
 * neighbourhood, a ward, a city, a province. The user wants to *see* the one
 * they are in, so the request carries the area's uid (the outline is fetched
 * from the API by uid) and a nonce, so that asking twice for the same area is
 * a new request (the map would otherwise ignore an identical target).
 */
export interface GeoFocusRequest {
  uid: string
  name: string
  kind: string
  source: string
  nonce: number
}

/**
 * The catchment outline of a school, drawn on the map.
 *
 * A school is more than a point — it serves an *area*, and the area is the
 * interesting part of it. Picking a school puts that outline on the map, in
 * the same orange the schools app draws it in, so the shape looks the same in
 * both apps of the whereq universe.
 */
export interface SchoolBoundaryRequest {
  schoolId: number
  name: string
  geometry: GeoGeometry
  nonce: number
}

interface MapContextValue {
  mapStyle: MapStyle
  setMapStyle: (s: MapStyle) => void
  filters: MapFilters
  setFilters: React.Dispatch<React.SetStateAction<MapFilters>>
  categories: string[]
  setCategories: React.Dispatch<React.SetStateAction<string[]>>
  /** Selected food sub-categories (OSM cuisine ids). Empty = all food. */
  cuisines: string[]
  setCuisines: React.Dispatch<React.SetStateAction<string[]>>
  essentials: MapEssentials
  setEssentials: React.Dispatch<React.SetStateAction<MapEssentials>>
  selectedSchool: string | null
  setSelectedSchool: (id: string | null) => void
  /** Current map viewport as "minLng,minLat,maxLng,maxLat" (drives viewport counts). */
  mapBbox: string | null
  setMapBbox: (b: string | null) => void
  /** Current map center (drives neighborhood detection + insights). */
  mapCenter: { lat: number; lng: number } | null
  setMapCenter: (c: { lat: number; lng: number } | null) => void
  showNeighborhood: boolean
  setShowNeighborhood: (v: boolean) => void
  sidebarCollapsed: boolean
  setSidebarCollapsed: (v: boolean) => void
  logoVariant: LogoVariant
  accent: string
  /** The latest "pan the map to this place" request. It lives in the context
   *  (not a window event) so it survives navigation: the map page can mount
   *  *after* the request was made and still honour it. */
  focusRequest: MapFocusRequest | null
  requestFocus: (f: { lat: number; lng: number; name?: string }) => void
  /** Drop the pending request once the map has consumed it. */
  clearFocus: () => void
  /** The place the user picked — a marker click or a search result. */
  selection: MapSelection | null
  /** Open the search modal on a place that is already on the map. */
  selectPlace: (s: MapSelection) => void
  /** Pan to a place, drop a search pin on it and open its card. */
  focusSelection: (s: MapSelection) => void
  /** The search modal: is it open, and what is it showing? */
  searchOpen: boolean
  searchMode: SearchMode
  openSearch: (mode: SearchMode, selection?: MapSelection) => void
  closeSearch: () => void
  /**
   * The place whose card was dismissed, or null. While it is set, the map
   * offers a control to bring that card back.
   */
  dismissedSelection: MapSelection | null
  /** Bring back the card of the dismissed place. */
  reopenSearch: () => void
  /** The pin a search leaves on the map (it stays until the next search). */
  searchPin: MapSelection | null
  setSearchPin: (s: MapSelection | null) => void
  /** The administrative area the user asked to see outlined on the map. */
  geoFocus: GeoFocusRequest | null
  /** Outline one administrative area (a ward, a neighbourhood, a city …). */
  requestGeoFocus: (a: { uid: string; name: string; kind: string; source: string }) => void
  /** Drop the outline once the map has drawn it (or the user dismissed it). */
  clearGeoFocus: () => void
  /** The catchment of the picked school, drawn on the map. */
  schoolBoundary: SchoolBoundaryRequest | null
  /** Draw a school's catchment outline. */
  requestSchoolBoundary: (b: { schoolId: number; name: string; geometry: GeoGeometry }) => void
  /** Drop the catchment outline (a different place was picked). */
  clearSchoolBoundary: () => void
}

const MapContext = createContext<MapContextValue | null>(null)

export function MapProvider({ children }: { children: ReactNode }) {
  const [mapStyle, setMapStyle] = useState<MapStyle>('streets')
  const [filters, setFilters] = useState<MapFilters>({
    friends: false, memorial: false, hazards: false,
    guides: false, routes: false, weather: false,
    areas: false,
  })
  // Start clean — no categories on by default (the user opts in; otherwise the
  // map floods with marker clusters).
  const [categories, setCategories] = useState<string[]>([])
  // Food sub-category preference, persisted locally (a first step toward saving
  // per-user preferences server-side later).
  const [cuisines, setCuisines] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('whereq:cuisines') || '[]') } catch { return [] }
  })
  useEffect(() => {
    try { localStorage.setItem('whereq:cuisines', JSON.stringify(cuisines)) } catch { /* ignore */ }
  }, [cuisines])
  const [essentials, setEssentials] = useState<MapEssentials>({
    schools: false, pharmacies: false, clinics: false, plazas: false, libraries: false,
  })
  const [selectedSchool, setSelectedSchool] = useState<string | null>(null)
  const [mapBbox, setMapBbox] = useState<string | null>(null)
  const [mapCenter, setMapCenter] = useState<{ lat: number; lng: number } | null>(null)
  const [showNeighborhood, setShowNeighborhood] = useState(true)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  // Focus requests (a search result → pan the map). The provider sits above
  // the router, so a request made on /schools is still pending when the map
  // page mounts.
  const [focusRequest, setFocusRequest] = useState<MapFocusRequest | null>(null)
  const focusNonce = useRef(0)
  const requestFocus = useCallback((f: { lat: number; lng: number; name?: string }) => {
    focusNonce.current += 1
    setFocusRequest({ lat: f.lat, lng: f.lng, name: f.name, nonce: focusNonce.current })
  }, [])
  const clearFocus = useCallback(() => setFocusRequest(null), [])

  // The picked place + the search modal. The modal lives here (not in the
  // header) so a marker click deep inside a map layer can open it.
  const [selection, setSelection] = useState<MapSelection | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchMode, setSearchMode] = useState<SearchMode>('all')
  const [searchPin, setSearchPin] = useState<MapSelection | null>(null)

  /**
   * The place whose card was dismissed — the way back to it.
   *
   * The card covers the middle of the map, and the map may be showing
   * something the card hides (an administrative boundary, for one), so the
   * user closes the card to look. It must not be a one-way street: as long as
   * the user is still on the same result — no new search, no other place —
   * the way back has to stay open. A new search or a new pick replaces it.
   */
  const [dismissed, setDismissedState] = useState<MapSelection | null>(null)
  // The same value in a ref, so the callbacks below can read it without
  // putting side effects inside a state updater (React may run an updater
  // more than once).
  const dismissedRef = useRef<MapSelection | null>(null)
  const setDismissed = useCallback((s: MapSelection | null) => {
    dismissedRef.current = s
    setDismissedState(s)
  }, [])

  // The current mode and selection, readable from the callbacks below without
  // making them depend on state that changes on every keystroke.
  const searchModeRef = useRef<SearchMode>(searchMode)
  searchModeRef.current = searchMode
  const selectionRef = useRef<MapSelection | null>(selection)
  selectionRef.current = selection

  // The administrative area the user asked to see outlined ("contained in →
  // Kensington-Chinatown → show me"). It lives in the context, like the focus
  // request, so it survives navigation: the map page can mount *after* the
  // request was made and still draw the outline.
  const [geoFocus, setGeoFocus] = useState<GeoFocusRequest | null>(null)
  const geoNonce = useRef(0)
  const requestGeoFocus = useCallback((a: { uid: string; name: string; kind: string; source: string }) => {
    geoNonce.current += 1
    setGeoFocus({ ...a, nonce: geoNonce.current })
  }, [])
  const clearGeoFocus = useCallback(() => setGeoFocus(null), [])

  // The catchment outline of the picked school. Like the geo focus, it lives in
  // the context so it survives the card being closed: the user closes the card
  // precisely to *see* the shape, and it must still be there.
  const [schoolBoundary, setSchoolBoundary] = useState<SchoolBoundaryRequest | null>(null)
  const schoolNonce = useRef(0)
  const requestSchoolBoundary = useCallback((b: { schoolId: number; name: string; geometry: GeoGeometry }) => {
    schoolNonce.current += 1
    setSchoolBoundary({ ...b, nonce: schoolNonce.current })
  }, [])
  const clearSchoolBoundary = useCallback(() => setSchoolBoundary(null), [])

  /** Open the card of something that is already on the map. */
  const selectPlace = useCallback((s: MapSelection) => {
    setSelection(s)
    // Another place is now the one the user is looking at: the way back to
    // the previous card goes with it.
    setDismissed(null)
    setSearchMode('place')
    setSearchOpen(true)
  }, [])

  /** Open a search result: pan to it, leave a pin on it, open its card. */
  const focusSelection = useCallback((s: MapSelection) => {
    setSearchPin(s)
    selectPlace(s)
    focusNonce.current += 1
    setFocusRequest({ lat: s.lat, lng: s.lng, name: s.name, nonce: focusNonce.current })
  }, [selectPlace])

  const openSearch = useCallback((mode: SearchMode, sel?: MapSelection) => {
    setSearchMode(mode)
    if (sel) setSelection(sel)
    // A new search replaces the result the user was looking at, so the way
    // back to that card goes away with it.
    setDismissed(null)
    setSearchOpen(true)
  }, [])

  const closeSearch = useCallback(() => {
    // Dismissing the card of a place leaves the way back to it open — the
    // user is still looking at that place, they just closed the card. A
    // *new* search or a new pick replaces it (see `selectPlace`).
    if (searchModeRef.current === 'place' && selectionRef.current) {
      setDismissed(selectionRef.current)
    }
    setSearchOpen(false)
  }, [])

  /** Bring back the card of the place whose card was dismissed. */
  const reopenSearch = useCallback(() => {
    const s = dismissedRef.current
    if (!s) return
    setDismissed(null)
    setSelection(s)
    setSearchMode('place')
    setSearchOpen(true)
  }, [])

  const logoVariant: LogoVariant = 'mono'
  const accent = '#4ADE80'

  return (
    <MapContext.Provider value={{
      mapStyle, setMapStyle,
      filters, setFilters,
      categories, setCategories,
      cuisines, setCuisines,
      essentials, setEssentials,
      selectedSchool, setSelectedSchool,
      mapBbox, setMapBbox,
      mapCenter, setMapCenter,
      showNeighborhood, setShowNeighborhood,
      sidebarCollapsed, setSidebarCollapsed,
      logoVariant, accent,
      focusRequest, requestFocus, clearFocus,
      selection, selectPlace, focusSelection,
      searchOpen, searchMode, openSearch, closeSearch,
      dismissedSelection: dismissed, reopenSearch,
      searchPin, setSearchPin,
      geoFocus, requestGeoFocus, clearGeoFocus,
      schoolBoundary, requestSchoolBoundary, clearSchoolBoundary,
    }}>
      {children}
    </MapContext.Provider>
  )
}

export function useMapContext() {
  const ctx = useContext(MapContext)
  if (!ctx) throw new Error('useMapContext must be used within MapProvider')
  return ctx
}
