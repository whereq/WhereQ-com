import { useCallback, useEffect, useRef, useState } from 'react'
import { Map as GoogleMap, useMap, useMapsLibrary } from '@vis.gl/react-google-maps'
import { MarkerClusterer, SuperClusterAlgorithm, type Cluster } from '@googlemaps/markerclusterer'
import { clusterIconUrl, clusterSize } from '@/components/map/localMarkers'
import { idealText } from '@/components/map/popupCard'
import { ANCHOR_CENTER, withModernListener } from '@/components/map/advancedMarkers'
import { schoolsApi } from '../api'
import { schoolColor } from '../colors'
import type { ScStrings } from '../i18n'
import type { CatchmentHit, MapPin, SchoolDetail, SchoolFilters } from '../types'

const MAP_ID = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID ?? ''
const PIN_CAP = 3000
// Fixed catchment-boundary color (decoupled from pin/type colors): orange,
// high contrast against the map's blue roads/water and green parks.
const BOUNDARY_COLOR = '#F97316'
// Cluster bubble: the same amber the main map uses for school clusters,
// so the two views of the same data look alike.
const CLUSTER_COLOR = '#E6B450'
// Pins within this many pixels of each other are one cluster.
const CLUSTER_RADIUS = 80
// Above this zoom the clusters dissolve and every school gets its own pin.
const CLUSTER_MAX_ZOOM = 16

function pinColor(p: MapPin): string {
  return schoolColor({ type: p.type, board_type: p.board_type })
}

/** A school pin — the DOM content of an advanced marker. */
function pinContent(color: string, selected: boolean): HTMLElement {
  const el = document.createElement('div')
  el.className = 'sc-pin'
  el.style.width = `${selected ? 14 : 10}px`
  el.style.height = `${selected ? 14 : 10}px`
  el.style.background = color
  return el
}

/** A cluster bubble — the amber tile the main map draws, with the count on it. */
function clusterContent(count: number): HTMLElement {
  const size = clusterSize(count)
  const el = document.createElement('div')
  el.className = 'sc-cluster'
  el.style.width = `${size}px`
  el.style.height = `${size}px`
  el.style.backgroundImage = `url("${clusterIconUrl(size, CLUSTER_COLOR)}")`
  el.style.backgroundSize = '100% 100%'
  el.style.backgroundRepeat = 'no-repeat'
  el.style.fontSize = count < 100 ? '12px' : '11px'
  el.style.color = idealText(CLUSTER_COLOR)
  el.textContent = String(count)
  return el
}

/** The always-on-top marker for the selected school. */
function selectedContent(color: string): HTMLElement {
  const el = document.createElement('div')
  el.className = 'sc-pin sc-pin--hl sc-pin--drop'
  el.style.width = '18px'
  el.style.height = '18px'
  el.style.background = color
  return el
}

/** Imperative marker + boundary + click layer driven by map idle / props. */
function MapLayer({ t, filters, query, selected, showBoundary, cluster, canBoundary, onGated, focusBounds, focusNonce, onSelect, onAtPoint }: {
  t: ScStrings; filters: SchoolFilters; query: string
  selected: SchoolDetail | null; showBoundary: boolean; cluster: boolean
  canBoundary: boolean; onGated: () => void
  focusBounds: [number, number, number, number] | null; focusNonce: number
  onSelect: (id: number) => void
  onAtPoint: (hits: CatchmentHit[], at: { lat: number; lng: number }) => void
}) {
  const map = useMap()
  // The marker library is loaded on demand; AdvancedMarkerElement needs it.
  const AdvancedMarkerElement = useMapsLibrary('marker')?.AdvancedMarkerElement
  const markers = useRef<Map<number, google.maps.marker.AdvancedMarkerElement>>(new Map())
  const bigPins = useRef<Set<number>>(new Set())
  const polys = useRef<google.maps.Polygon[]>([])
  const selMarker = useRef<google.maps.marker.AdvancedMarkerElement | null>(null)
  const reqId = useRef(0)
  const clusterer = useRef<MarkerClusterer | null>(null)
  const [count, setCount] = useState(0)
  const [capped, setCapped] = useState(false)

  // The clustering mode of the latest render. The pin effect reads this
  // instead of taking `cluster` as a dependency, so flipping the toggle
  // re-places the pins we already have instead of refetching the viewport.
  const clusterOn = useRef(cluster)
  useEffect(() => { clusterOn.current = cluster }, [cluster])

  // The clusterer owns the pins while clustering is on: it draws the bubbles
  // and puts the individual schools back on the map as you zoom in.
  useEffect(() => {
    if (!map || !AdvancedMarkerElement) return
    const renderer = {
      render: (c: Cluster) => withModernListener(new AdvancedMarkerElement({
        position: c.position,
        content: clusterContent(c.count),
        title: `${c.count} schools`,
        zIndex: 100 + c.count,
        gmpClickable: true,
        ...ANCHOR_CENTER,
      })),
    }
    const c = new MarkerClusterer({
      map,
      renderer,
      algorithm: new SuperClusterAlgorithm({ radius: CLUSTER_RADIUS, maxZoom: CLUSTER_MAX_ZOOM }),
      onClusterClick: (_e, cluster, m) => {
        const b = cluster.bounds
        if (b) m.fitBounds(b, 80)
      },
    })
    clusterer.current = c
    return () => { c.clearMarkers(); clusterer.current = null }
  }, [map, AdvancedMarkerElement])

  // Place the pins: grouped into cluster bubbles when the toggle is on, one
  // marker per school when it is off.
  const applyMarkers = useCallback((m: google.maps.Map) => {
    const c = clusterer.current
    if (!c) return
    const all = [...markers.current.values()]
    if (clusterOn.current) {
      c.clearMarkers(true)
      c.addMarkers(all)
    } else {
      // clearMarkers() (with the redraw) is what takes the old bubbles off
      // the map — clearMarkers(true) would leave them behind.
      c.clearMarkers()
      for (const mk of all) mk.map = m
    }
  }, [])

  // The toggle flipped: re-place the pins we already have — no refetch.
  useEffect(() => {
    if (!map) return
    applyMarkers(map)
  }, [map, cluster, applyMarkers])

  // refetch pins for the current viewport (debounced on idle)
  useEffect(() => {
    if (!map || !AdvancedMarkerElement) return
    let timer: number
    const fetchPins = () => {
      const b = map.getBounds()
      if (!b) return
      const ne = b.getNorthEast(), sw = b.getSouthWest()
      const bbox = `${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`
      const id = ++reqId.current
      schoolsApi.mapPins({ filters, q: query, bbox, limit: PIN_CAP + 1 }).then((pins) => {
        if (id !== reqId.current || !map) return
        const cap = pins.length > PIN_CAP
        const shown = cap ? pins.slice(0, PIN_CAP) : pins
        setCapped(cap); setCount(pins.length)
        const next = new Set(shown.map((p) => p.id))
        // remove stale
        for (const [mid, mk] of markers.current) {
          if (!next.has(mid)) {
            mk.map = null
            markers.current.delete(mid)
            bigPins.current.delete(mid)
          }
        }
        // add / update
        for (const p of shown) {
          let mk = markers.current.get(p.id)
          const color = pinColor(p)
          const isSelected = p.id === selected?.id
          if (!mk) {
            // No `map` here: while clustering is on the clusterer owns the
            // placement, and applyMarkers() puts the pin on the map itself
            // when the toggle is off.
            mk = new AdvancedMarkerElement({
              position: { lat: p.lat, lng: p.lng },
              content: pinContent(color, isSelected),
              title: p.name,
              zIndex: 1,
              // Advanced markers are not clickable unless asked to be.
              gmpClickable: true,
              ...ANCHOR_CENTER,
            })
            // Advanced markers fire 'gmp-click' — and they want the modern
            // addEventListener, not the deprecated addListener.
            mk.addEventListener('gmp-click', () => onSelect(p.id))
            markers.current.set(p.id, mk)
            if (isSelected) bigPins.current.add(p.id)
          } else if (bigPins.current.has(p.id) !== isSelected) {
            // Only the selected school's pin is drawn larger.
            mk.content = pinContent(color, isSelected)
            if (isSelected) bigPins.current.add(p.id)
            else bigPins.current.delete(p.id)
          }
        }
        applyMarkers(map)
      }).catch(() => {})
    }
    const onIdle = () => { window.clearTimeout(timer); timer = window.setTimeout(fetchPins, 250) }
    const l = map.addListener('idle', onIdle)
    fetchPins()
    return () => { window.clearTimeout(timer); l.remove() }
  }, [map, filters, query, selected?.id, applyMarkers, AdvancedMarkerElement])

  // boundary polygons of the selected school
  useEffect(() => {
    if (!map) return
    polys.current.forEach((p) => p.setMap(null)); polys.current = []
    if (!showBoundary || !selected?.boundary_geojson) return
    for (const polygon of selected.boundary_geojson.coordinates) {
      const paths = polygon.map((ring) => ring.map(([lng, lat]) => ({ lat, lng })))
      polys.current.push(new window.google.maps.Polygon({
        paths, map, strokeColor: BOUNDARY_COLOR, strokeOpacity: 0.95, strokeWeight: 3.5,
        fillColor: BOUNDARY_COLOR, fillOpacity: 0.12, clickable: false, zIndex: 0,
      }))
    }
    return () => { polys.current.forEach((p) => p.setMap(null)); polys.current = [] }
  }, [map, selected, showBoundary])

  // highlight the selected school with a dedicated, always-on-top marker that
  // drops in — so it's unmistakable which school is selected, even before the
  // viewport pin layer has (re)loaded around it.
  useEffect(() => {
    if (!map || !AdvancedMarkerElement) return
    if (selMarker.current) { selMarker.current.map = null; selMarker.current = null }
    if (!selected || selected.lat == null || selected.lng == null) return
    const color = schoolColor({ type: selected.type, board_type: selected.board?.type, programs: selected.programs })
    const mk = new AdvancedMarkerElement({
      position: { lat: selected.lat, lng: selected.lng },
      content: selectedContent(color),
      title: selected.name,
      zIndex: 10000,
      ...ANCHOR_CENTER,
    })
    mk.map = map
    selMarker.current = mk
    return () => { if (selMarker.current) { selMarker.current.map = null; selMarker.current = null } }
  }, [map, selected?.id, AdvancedMarkerElement])

  // recenter on selection — fit the whole catchment when we have a boundary,
  // otherwise just center the school point
  useEffect(() => {
    if (!map || !selected) return
    if (showBoundary && selected.boundary_geojson) {
      const b = new window.google.maps.LatLngBounds()
      for (const poly of selected.boundary_geojson.coordinates)
        for (const ring of poly)
          for (const [lng, lat] of ring) b.extend({ lat, lng })
      if (!b.isEmpty()) { map.fitBounds(b, 56); return }
    }
    if (selected.lat != null && selected.lng != null) {
      map.panTo({ lat: selected.lat, lng: selected.lng })
      if ((map.getZoom() ?? 0) < 13) map.setZoom(14)
    }
  }, [map, selected?.id, showBoundary])

  // explicit "Search" → fly the map to the extent of the matching schools
  // (e.g. selecting a school board relocates the map to that board's area).
  useEffect(() => {
    if (!map || !focusBounds) return
    const [minLat, minLng, maxLat, maxLng] = focusBounds
    if (minLat === maxLat && minLng === maxLng) {
      map.panTo({ lat: minLat, lng: minLng })
      if ((map.getZoom() ?? 0) < 13) map.setZoom(14)
      return
    }
    const b = new window.google.maps.LatLngBounds(
      { lat: minLat, lng: minLng }, { lat: maxLat, lng: maxLng },
    )
    if (!b.isEmpty()) map.fitBounds(b, 64)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, focusNonce])

  // click empty map → which catchments cover this point (boundary data: gated)
  useEffect(() => {
    if (!map) return
    const l = map.addListener('click', (e: google.maps.MapMouseEvent) => {
      const ll = e.latLng; if (!ll) return
      if (!canBoundary) { onGated(); return }
      const at = { lat: ll.lat(), lng: ll.lng() }
      schoolsApi.at(at.lat, at.lng).then((hits) => onAtPoint(hits, at)).catch(() => {})
    })
    return () => l.remove()
  }, [map, canBoundary])

  return (
    <>
      <span className="sc-mapcount">{count.toLocaleString()} {t.results}</span>
      {capped && cluster && <span className="sc-zoomhint">{t.zoomHint}</span>}
    </>
  )
}

export function SchoolMap({ t, theme, filters, query, selected, showBoundary, cluster, center, canBoundary, onGated, focusBounds, focusNonce, onSelect, onAtPoint }: {
  t: ScStrings; theme: 'light' | 'dark'; filters: SchoolFilters; query: string
  selected: SchoolDetail | null; showBoundary: boolean; cluster: boolean
  center: { lat: number; lng: number }
  canBoundary: boolean; onGated: () => void
  focusBounds: [number, number, number, number] | null; focusNonce: number
  onSelect: (id: number) => void
  onAtPoint: (hits: CatchmentHit[], at: { lat: number; lng: number }) => void
}) {
  return (
    <div className="sc-map">
      <GoogleMap
        defaultCenter={center}
        defaultZoom={12}
        mapId={MAP_ID}
        colorScheme={theme === 'dark' ? 'DARK' : 'LIGHT'}
        gestureHandling="greedy"
        disableDefaultUI={false}
        clickableIcons={false}
        style={{ width: '100%', height: '100%' }}
      >
        <MapLayer t={t} filters={filters} query={query} selected={selected} showBoundary={showBoundary}
          cluster={cluster} canBoundary={canBoundary} onGated={onGated}
          focusBounds={focusBounds} focusNonce={focusNonce} onSelect={onSelect} onAtPoint={onAtPoint} />
      </GoogleMap>
    </div>
  )
}
