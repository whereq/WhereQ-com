import { useState, useEffect, useRef } from 'react'
import {
  Map,
  AdvancedMarker,
  MapCameraChangedEvent,
  useMap,
} from '@vis.gl/react-google-maps'
import { useMapContext } from '@/contexts/MapContext'
import { useDayNight } from '@/hooks/useDayNight'
import { LocalContentLayer } from './LocalContentLayer'
import { PlacesLayer } from './PlacesLayer'
import { SchoolsLayer } from './SchoolsLayer'
import { HazardsLayer } from './HazardsLayer'
import { GeoAreasLayer } from './GeoAreasLayer'
import { GeoFocusLayer } from './GeoFocusLayer'
import { SchoolBoundaryLayer } from './SchoolBoundaryLayer'
import type { MapPin, MapEssentials } from '@/types/map'
import type { MapSelection } from '@/types/selection'

// Kinds owned by dedicated viewport-driven layers, so they are not also drawn
// as individual AdvancedMarkers from the global pin set.
const LAYER_MANAGED_KINDS = new Set(['pharmacy', 'clinic', 'plaza', 'library', 'poi', 'school', 'hazard'])

const MAP_ID = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID ?? ''

// Toronto, Ontario, Canada
const DEFAULT_CENTER = { lat: 43.6532, lng: -79.3832 }
const DEFAULT_ZOOM = 14

// Map MapStyle to Google Maps type IDs
const STYLE_TO_TYPE: Record<string, string> = {
  streets: 'roadmap',
  satellite: 'satellite',
  terrain: 'terrain',
  transit: 'roadmap',
}

// ── Pin marker components ──────────────────────────────────────

function MeMarker() {
  return (
    <div style={{ position: 'relative', width: 24, height: 24 }}>
      <div style={{
        position: 'absolute', inset: -8,
        borderRadius: '50%',
        background: 'var(--accent)',
        opacity: 0.2,
        animation: 'pulse 2.4s ease-in-out infinite',
      }} />
      <div style={{
        width: 24, height: 24,
        borderRadius: '50%',
        background: 'var(--accent)',
        border: '3px solid white',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 2px 8px rgba(0,0,0,.3)',
      }}>
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'white' }} />
      </div>
    </div>
  )
}

function FriendMarker({ pin }: { pin: MapPin }) {
  const dim = pin.status === 'idle'
  return (
    <div style={{
      width: 32, height: 32,
      borderRadius: '50%',
      background: 'var(--surface)',
      border: '2px solid var(--social)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      opacity: dim ? 0.85 : 1,
      position: 'relative',
      boxShadow: '0 2px 8px rgba(0,0,0,.3)',
    }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', fontFamily: 'var(--font-display)' }}>
        {pin.initial}
      </span>
      <div style={{
        position: 'absolute', top: -2, right: -2,
        width: 10, height: 10, borderRadius: '50%',
        background: dim ? 'var(--warn)' : 'var(--success)',
        border: '2px solid var(--surface)',
      }} />
    </div>
  )
}

function MemorialMarker() {
  return (
    <div style={{
      width: 0, height: 0, position: 'relative',
      filter: 'drop-shadow(0 2px 4px rgba(0,0,0,.3))',
    }}>
      <svg width="28" height="34" viewBox="-14 -22 28 34" style={{ overflow: 'visible' }}>
        <path d="M0 -20 C -10 -20 -14 -12 -14 -6 C -14 4 0 12 0 12 C 0 12 14 4 14 -6 C 14 -12 10 -20 0 -20 Z"
          fill="var(--memorial)" stroke="white" strokeWidth="1.5" />
        <circle cx="0" cy="-7" r="4.5" fill="white" />
      </svg>
    </div>
  )
}

function HazardMarker() {
  return (
    <div style={{ filter: 'drop-shadow(0 2px 4px rgba(0,0,0,.3))' }}>
      <svg width="24" height="22" viewBox="-12 -13 24 22">
        <polygon points="0,-12 11,8 -11,8" fill="var(--danger)" stroke="white" strokeWidth="1.5" />
        <text y="6" textAnchor="middle" fontSize="9" fontWeight="700" fill="white" fontFamily="var(--font-display)">!</text>
      </svg>
    </div>
  )
}

function PoiMarker({ cat }: { cat: string }) {
  const colors: Record<string, string> = { coffee: '#A0763C', food: '#FF7A4D', parking: '#5BA5FF', fuel: '#4ADE80', gas: '#F59E0B' }
  const icons: Record<string, string> = { coffee: '\u2615', food: '\uD83C\uDF5C', parking: 'P', fuel: '\u26FD', gas: '\u26FD' }
  return (
    <div style={{
      width: 22, height: 22, borderRadius: '50%',
      background: colors[cat] || 'var(--text)',
      border: '2px solid var(--surface)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: cat === 'parking' ? 11 : 10,
      fontWeight: 700,
      color: 'white',
      boxShadow: '0 2px 6px rgba(0,0,0,.3)',
    }}>
      {icons[cat] || ''}
    </div>
  )
}

function SavedMarker({ color }: { color?: string }) {
  return (
    <div style={{ filter: 'drop-shadow(0 1px 3px rgba(0,0,0,.3))' }}>
      <svg width="16" height="16" viewBox="-10 -10 20 20">
        <path d="M0 -9 L 2 -4 L 7 -4 L 3 -1 L 5 4 L 0 1 L -5 4 L -3 -1 L -7 -4 L -2 -4 Z"
          fill={color || 'var(--accent)'} stroke="white" strokeWidth="1" />
      </svg>
    </div>
  )
}

function SchoolMarker({ pin }: { pin: MapPin }) {
  const LEVELS: Record<string, { fill: string; lab: string }> = {
    elem: { fill: '#E6B450', lab: 'E' },
    k8: { fill: '#E6B450', lab: 'K8' },
    middle: { fill: '#E89A3C', lab: 'M' },
    high: { fill: '#E07A2E', lab: 'H' },
    college: { fill: '#C44F4F', lab: 'CC' },
    uni: { fill: '#A03A56', lab: 'U' },
  }
  const L = LEVELS[pin.level || 'elem']
  return (
    <div style={{
      width: 26, height: 26, borderRadius: 3,
      background: L.fill, border: '2px solid white',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: L.lab.length > 1 ? 9 : 12, fontWeight: 800,
      color: '#2A1F0A', fontFamily: 'var(--font-display)',
      boxShadow: '0 2px 6px rgba(0,0,0,.3)',
    }}>
      {L.lab}
    </div>
  )
}

function PharmacyMarker() {
  return (
    <div style={{
      width: 24, height: 24, borderRadius: '50%',
      background: '#34D399', border: '2px solid white',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 14, fontWeight: 700, color: 'white',
      boxShadow: '0 2px 6px rgba(0,0,0,.3)',
    }}>
      +
    </div>
  )
}

function ClinicMarker() {
  return (
    <div style={{
      width: 24, height: 24, borderRadius: '50%',
      background: '#F87171', border: '2px solid white',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 14, fontWeight: 700, color: 'white',
      boxShadow: '0 2px 6px rgba(0,0,0,.3)',
    }}>
      +
    </div>
  )
}

function PlazaMarker() {
  return (
    <div style={{
      width: 20, height: 20,
      background: '#FB923C', border: '2px solid white',
      transform: 'rotate(45deg)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: '0 2px 6px rgba(0,0,0,.3)',
    }}>
      <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'white', transform: 'rotate(-45deg)' }} />
    </div>
  )
}

function LibraryMarker() {
  return (
    <div style={{
      width: 24, height: 20, borderRadius: 3,
      background: '#818CF8', border: '2px solid white',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, color: 'white',
      boxShadow: '0 2px 6px rgba(0,0,0,.3)',
    }}>
      <svg width="12" height="10" viewBox="0 0 12 10" fill="none" stroke="white" strokeWidth="1.2">
        <path d="M1 1 V 9 M 6 1 V 9 M 11 1 V 9" />
        <path d="M1 1 H 11 M 1 9 H 11" />
      </svg>
    </div>
  )
}

/**
 * The pin a search leaves on the map — a teardrop in the place's colour.
 *
 * The colour is applied as a style, not as an SVG `fill` attribute: a
 * presentation attribute does not resolve `var(--x)`.
 *
 * There is no button inside the marker on purpose — the Maps API listens for
 * the click on the marker element, so a button in here would have to fight it.
 * The pin is removed from the place card ("Remove pin") instead.
 *
 * `badge` marks the pin as the **way back** to a card the user dismissed:
 * the card covers the middle of the map, so it gets closed to look at what is
 * underneath — and the pin they were looking at is where they would look for
 * it again.
 */
function SearchPinMarker({ color, badge }: { color: string; badge?: boolean }) {
  return (
    <div style={{ filter: 'drop-shadow(0 2px 4px rgba(0,0,0,.35))', position: 'relative' }}>
      <svg width="30" height="36" viewBox="-15 -24 30 36" style={{ overflow: 'visible' }}>
        <path d="M0 -22 C -11 -22 -15 -13 -15 -6 C -15 5 0 14 0 14 C 0 14 15 5 15 -6 C 15 -13 11 -22 0 -22 Z"
          style={{ fill: color }} stroke="white" strokeWidth="2" />
        <circle cx="0" cy="-7" r="4.5" fill="white" />
      </svg>
      {badge && (
        <span
          className="search-pin-badge"
          title="Show the card again"
          aria-hidden="true"
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12a9 9 0 1 0 3-6.7" />
            <path d="M3 4v5h5" />
          </svg>
        </span>
      )}
    </div>
  )
}

// ── Render a single pin marker ─────────────────────────────────

function PinMarkerContent({ pin }: { pin: MapPin }) {
  switch (pin.kind) {
    case 'me': return <MeMarker />
    case 'friend': return <FriendMarker pin={pin} />
    case 'memorial': return <MemorialMarker />
    case 'hazard': return <HazardMarker />
    case 'poi': return <PoiMarker cat={pin.cat || ''} />
    case 'saved': return <SavedMarker color={pin.color} />
    case 'school': return <SchoolMarker pin={pin} />
    case 'pharmacy': return <PharmacyMarker />
    case 'clinic': return <ClinicMarker />
    case 'plaza': return <PlazaMarker />
    case 'library': return <LibraryMarker />
    default: return null
  }
}

// ── Tooltip on hover ───────────────────────────────────────────

function PinTooltip({ title }: { title: string }) {
  return (
    <div style={{
      position: 'absolute',
      bottom: '100%',
      left: '50%',
      transform: 'translateX(-50%)',
      marginBottom: 6,
      background: 'rgba(15,20,27,.95)',
      border: '1px solid var(--border)',
      borderRadius: 2,
      padding: '4px 8px',
      fontSize: 11,
      color: 'var(--text)',
      whiteSpace: 'nowrap',
      pointerEvents: 'none',
    }}>
      {title}
    </div>
  )
}

// ── Main GoogleMapView component ───────────────────────────────

interface GoogleMapViewProps {
  pins: MapPin[]
  showFriends: boolean
  showMemorial: boolean
  showHazards: boolean
  /** The administrative-areas layer (cities, wards, neighbourhoods). */
  showAreas: boolean
  showCategories: string[]
  neighborhoodEssentials: MapEssentials
  onSelectMemorial: (p: MapPin) => void
  onSelectSchool: (p: MapPin) => void
  /** A pin of the global set was picked (me / friend / memorial). */
  onSelectPin: (p: MapPin) => void
  /** A layer marker was picked — the map opens that place's card. */
  onSelectPlace: (sel: MapSelection) => void
  focusTarget?: { lat: number; lng: number } | null
  onFocusConsumed?: () => void
  /** User's geolocation (null until granted) — map centers here once on first fix. */
  userLocation?: { lat: number; lng: number } | null
  localTypes?: string[]
  localCategories?: string[]
  localSources?: string[]
  localFromIso?: string
  onLocalCount?: (n: number, capped: boolean) => void
}

export function GoogleMapView({
  pins,
  showFriends,
  showMemorial,
  showHazards,
  showAreas,
  showCategories,
  neighborhoodEssentials,
  onSelectMemorial,
  onSelectSchool,
  onSelectPin,
  onSelectPlace,
  focusTarget,
  onFocusConsumed,
  userLocation,
  localTypes = [],
  localCategories = [],
  localSources = [],
  localFromIso,
  onLocalCount,
}: GoogleMapViewProps) {
  const { mapStyle, setMapBbox, setMapCenter, cuisines, searchPin, selectPlace, dismissedSelection } = useMapContext()
  const map = useMap()
  const [hoveredPin, setHoveredPin] = useState<string | null>(null)
  const [center, setCenter] = useState(DEFAULT_CENTER)
  const [zoom, setZoom] = useState(DEFAULT_ZOOM)
  const didAutoCenter = useRef(false)
  const userMovedMap = useRef(false)

  // Pan to focus target when search selects a place
  useEffect(() => {
    if (focusTarget && map) {
      map.panTo(focusTarget)
      map.setZoom(16)
      onFocusConsumed?.()
    }
  }, [focusTarget, map, onFocusConsumed])

  // Note a genuine user pan so we don't yank the view if geolocation resolves late.
  useEffect(() => {
    if (!map) return
    const l = map.addListener('dragstart', () => { userMovedMap.current = true })
    return () => l.remove()
  }, [map])

  // Center on the user's location once, on the first fix (default stays Toronto
  // when geolocation is denied/unavailable).
  useEffect(() => {
    if (!map || didAutoCenter.current || userMovedMap.current || !userLocation) return
    didAutoCenter.current = true
    map.panTo(userLocation)
    map.setZoom(15)
  }, [map, userLocation])

  // Publish the settled viewport bbox so the sidebar can show viewport counts.
  useEffect(() => {
    if (!map) return
    const publish = () => {
      const b = map.getBounds()
      if (b) {
        const ne = b.getNorthEast(), sw = b.getSouthWest()
        setMapBbox(`${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`)
      }
      const c = map.getCenter()
      if (c) setMapCenter({ lat: c.lat(), lng: c.lng() })
    }
    const l = map.addListener('idle', publish)
    publish()
    return () => l.remove()
  }, [map, setMapBbox, setMapCenter])

  // Essentials kinds + quick-category POIs handled by the clustered PlacesLayer.
  const placeKinds = [
    neighborhoodEssentials.pharmacies && 'pharmacy',
    neighborhoodEssentials.clinics && 'clinic',
    neighborhoodEssentials.plazas && 'plaza',
    neighborhoodEssentials.libraries && 'library',
  ].filter(Boolean) as string[]

  const visiblePins = pins.filter(pin => {
    // Clustered layers own these kinds — don't double-render them here.
    if (LAYER_MANAGED_KINDS.has(pin.kind)) return false
    if (pin.kind === 'friend' && !showFriends) return false
    if (pin.kind === 'memorial' && !showMemorial) return false
    return true
  })

  const mapTypeId = STYLE_TO_TYPE[mapStyle] || 'roadmap'
  // Map theme follows the sun (day = light, night = dark) by default, based on
  // the current map location. Re-checked each minute so it flips at sunset.
  const colorScheme = useDayNight(center.lat, center.lng) ? 'LIGHT' : 'DARK'

  return (
    <>
      <Map
        key={colorScheme}
        defaultCenter={center}
        defaultZoom={zoom}
        mapId={MAP_ID}
        mapTypeId={mapTypeId}
        colorScheme={colorScheme}
        gestureHandling="greedy"
        disableDefaultUI={true}
        clickableIcons={false}
        style={{ width: '100%', height: '100%' }}
        onCameraChanged={(ev: MapCameraChangedEvent) => {
          const { center: c, zoom: z } = ev.detail
          setCenter(c)
          setZoom(z)
        }}
      >
        {visiblePins.map(pin => (
          <AdvancedMarker
            key={pin.id}
            position={{ lat: pin.lat, lng: pin.lng }}
            onClick={() => {
              if (pin.kind === 'memorial') { onSelectMemorial(pin); return }
              if (pin.kind === 'school') { onSelectSchool(pin); return }
              // Every other pin (me, friends) opens the same card.
              onSelectPin(pin)
            }}
          >
            <div
              style={{ position: 'relative', cursor: 'pointer' }}
              onMouseEnter={() => setHoveredPin(pin.id)}
              onMouseLeave={() => setHoveredPin(null)}
            >
              {hoveredPin === pin.id && pin.title && <PinTooltip title={pin.title} />}
              <PinMarkerContent pin={pin} />
            </div>
          </AdvancedMarker>
        ))}

        <PlacesLayer kinds={placeKinds} categories={showCategories} cuisines={cuisines} onSelect={onSelectPlace} />
        <SchoolsLayer enabled={neighborhoodEssentials.schools} onSelect={onSelectPlace} />
        <HazardsLayer enabled={showHazards} onSelect={onSelectPlace} />
        <GeoAreasLayer enabled={showAreas} onSelect={onSelectPlace} />
        <GeoFocusLayer onSelect={onSelectPlace} />
        <SchoolBoundaryLayer />

        <LocalContentLayer
          enabledTypes={localTypes}
          categories={localCategories}
          sources={localSources}
          fromIso={localFromIso}
          onCount={onLocalCount}
          onSelect={onSelectPlace}
        />

        {/* The pin a search leaves on the map. While the card is dismissed it
            wears the badge: the pin is the way back to it. */}
        {searchPin && (
          <AdvancedMarker
            position={{ lat: searchPin.lat, lng: searchPin.lng }}
            zIndex={2000}
            onClick={() => selectPlace(searchPin)}
          >
            <SearchPinMarker color={searchPin.color} badge={!!dismissedSelection} />
          </AdvancedMarker>
        )}
      </Map>

      {/* Coordinates overlay */}
      <div className="map-coords-live" style={{
        position: 'absolute', bottom: 8, left: 8,
        fontSize: 11, color: 'var(--muted)',
        pointerEvents: 'none',
        fontFamily: 'var(--font-mono, monospace)',
      }}>
        {center.lat.toFixed(4)}&deg; N &middot; {Math.abs(center.lng).toFixed(4)}&deg; W &middot; z{Math.round(zoom)}
      </div>
    </>
  )
}
