import type { GeoBoundary, GeoGeometry } from '@/types/geo'

/**
 * The shared vocabulary of the administrative-areas layers.
 *
 * Two layers draw outlines — the viewport layer (every area in view) and the
 * focus layer (the one area the user asked about) — so the colours, the
 * polygon maths and the centroid live here, once. A neighbourhood that is
 * amber in the viewport layer is amber when it is focused; a formal
 * (geoBoundaries) outline is violet in both.
 */

/** One colour per kind — the OpenStreetMap vocabulary. */
export const KIND_COLORS: Record<string, string> = {
  region: '#6FD3C7',
  municipality: '#4ADE80',
  city: '#4ADE80',
  town: '#4ADE80',
  district: '#E6B450',
  suburb: '#E6B450',
  ward: '#E6B450',
  neighbourhood: '#F59E0B',
}

/**
 * The geoBoundaries vocabulary gets its own hue.
 *
 * The feed keeps the two vocabularies side by side — a census subdivision and
 * an OSM city boundary describe the same town in two languages — and they
 * overlap on the map. Drawing them in the same colour would hide the
 * difference, so the formal one is violet and the crowd-mapped one keeps the
 * kind's own colour.
 */
export const GEOBOUNDARIES_COLOR = '#A78BFA'

/** The colour a kind falls back to. */
export const FALLBACK_COLOR = '#9CA3AF'

/** The colour an area is drawn in. */
export function colorForKind(kind: string, source: string): string {
  if (source === 'geoboundaries') return GEOBOUNDARIES_COLOR
  return KIND_COLORS[kind] ?? FALLBACK_COLOR
}

/**
 * Turn a GeoJSON geometry into the list of polygons Google Maps wants.
 *
 * A Polygon is one polygon; a MultiPolygon is several, each with its own
 * rings. Google Maps' `Polygon` takes *one* path per ring, so a multipolygon
 * has to be drawn as several polygons.
 */
export function polygonsOf(geometry: GeoGeometry): number[][][][] {
  if (geometry.type === 'Polygon') {
    return [geometry.coordinates]
  }
  return geometry.coordinates
}

/** A GeoJSON ring is [[lng,lat], …]; Google wants LatLngLiteral. */
export function toPath(ring: number[][]): google.maps.LatLngLiteral[] {
  return ring.map(([lng, lat]) => ({ lat, lng }))
}

/** Where the place is — the feed's own centroid, or the middle of the outline. */
export function centroidOf(b: GeoBoundary): { lat: number; lng: number } {
  if (b.centroid_lat != null && b.centroid_lon != null) {
    return { lat: b.centroid_lat, lng: b.centroid_lon }
  }
  const ring = polygonsOf(b.geometry)[0]?.[0] ?? []
  if (!ring.length) return { lat: 0, lng: 0 }
  let lat = 0
  let lng = 0
  for (const [x, y] of ring) { lng += x; lat += y }
  return { lat: lat / ring.length, lng: lng / ring.length }
}

/**
 * The bounding box of a geometry, as a Google Maps LatLngBounds.
 *
 * `fitBounds` needs the *span* of the shape, not its middle: a neighbourhood
 * that is 2 km across has to be seen from 2 km across, or the outline is a
 * smudge at the screen's edge.
 */
export function boundsOf(geometry: GeoGeometry): google.maps.LatLngBounds | null {
  let minLat = Infinity, minLng = Infinity
  let maxLat = -Infinity, maxLng = -Infinity
  let seen = false
  for (const polygon of polygonsOf(geometry)) {
    for (const ring of polygon) {
      for (const [lng, lat] of ring) {
        seen = true
        if (lat < minLat) minLat = lat
        if (lat > maxLat) maxLat = lat
        if (lng < minLng) minLng = lng
        if (lng > maxLng) maxLng = lng
      }
    }
  }
  if (!seen) return null
  return new window.google.maps.LatLngBounds(
    { lat: minLat, lng: minLng },
    { lat: maxLat, lng: maxLng },
  )
}

/** The padding every fit gets, so the shape is not glued to the edge. */
const FIT_MARGIN = 48

/**
 * Where the shape may be drawn so the user can actually see it.
 *
 * The place card covers the middle of the screen, and the map is behind it.
 * "Show me that area" must answer *on screen*: when the card is open the
 * shape is fitted into the free part of the map beside it, and when the card
 * is closed it is fitted to the middle, where it belongs.
 *
 * The padding is measured against the **map's own** box, not the window: the
 * sidebar covers the left of the window, and the map starts after it.
 */
export function fitPadding(
  map: google.maps.Map,
  cardEl: Element | null,
): google.maps.Padding {
  const base = { top: FIT_MARGIN, right: FIT_MARGIN, bottom: FIT_MARGIN, left: FIT_MARGIN }
  if (!cardEl) return base
  const mapRect = map.getDiv().getBoundingClientRect()
  const cardRect = cardEl.getBoundingClientRect()
  if (!mapRect.width || !cardRect.width) return base
  // The card's edges in the map's own coordinates.
  const cardLeft = cardRect.left - mapRect.left
  const cardRight = cardRect.right - mapRect.left
  const freeRight = mapRect.width - cardRight
  const freeLeft = cardLeft
  // Whichever side of the card has more room is where the shape goes.
  if (freeRight >= freeLeft && freeRight > 220) {
    return { ...base, left: Math.round(cardRight + 24) }
  }
  if (freeLeft > 220) {
    return { ...base, right: Math.round(mapRect.width - cardLeft + 24) }
  }
  return base
}
