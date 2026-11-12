import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useMap } from '@vis.gl/react-google-maps'
import { geoApi } from '@/lib/geoApi'
import type { GeoBoundary } from '@/types/geo'
import type { MapSelection } from '@/types/selection'
import { colorForKind, centroidOf, polygonsOf, toPath } from './geoStyles'

/**
 * The kinds drawn at each zoom level.
 *
 * The bands matter, and so does what is *missing*: the country and the
 * province are never drawn. Their outlines are enormous — Ontario is 65 000
 * points even after the simplification, because it is a multipolygon of 4 000
 * lakes and islands — and they are off-screen at every zoom where the area
 * layer is useful. The containment stack still reports them.
 *
 * A province-scale kind is not in the list either (a US state is the same
 * idea under another name), so the download shrinks with the viewport.
 */
const KINDS_BY_ZOOM: { minZoom: number; maxZoom: number | null; kinds: string[] }[] = [
  { minZoom: 0, maxZoom: 6, kinds: ['region', 'municipality', 'city', 'town'] },
  { minZoom: 7, maxZoom: 10, kinds: ['region', 'municipality', 'city', 'town', 'district', 'suburb'] },
  { minZoom: 11, maxZoom: null, kinds: ['municipality', 'city', 'town', 'district', 'suburb', 'ward', 'neighbourhood'] },
]

/**
 * How many outlines one request may carry.
 *
 * The server orders the areas smallest first, so a truncated answer drops the
 * large ones — the ones off-screen at street level — rather than the wards
 * and neighbourhoods the user is looking at.
 */
const OUTLINE_CAP = 600

/**
 * The administrative areas layer — the outlines of the cities, wards and
 * neighbourhoods the user is looking at.
 *
 * Fed by GET /geo/boundaries: one request per viewport, and the outlines come
 * back already simplified, because a neighbourhood polygon with 40 000 points
 * is not something a browser should download.
 *
 * Which kinds are drawn depends on the zoom: a province outline at street
 * level is just a line around the edge of the screen.
 */
export function GeoAreasLayer({
  enabled,
  onSelect,
}: {
  enabled: boolean
  onSelect: (sel: MapSelection) => void
}) {
  const map = useMap()
  const { t } = useTranslation()
  const polygons = useRef<Map<string, google.maps.Polygon[]>>(new Map())
  const reqId = useRef(0)
  // The pick handler is held in a ref: the outlines outlive a re-render, and
  // a polygon built under an older handler would call a stale callback.
  // The translator is kept beside it for the same reason — a language change
  // must not leave the outlines labelling themselves in the old language.
  const select = useRef(onSelect)
  select.current = onSelect
  const label = useRef(t)
  label.current = t

  const clearAll = () => {
    for (const [, list] of polygons.current) for (const p of list) p.setMap(null)
    polygons.current.clear()
  }

  // Tear down when the layer is switched off.
  useEffect(() => {
    if (!map || enabled) return
    // Invalidate any request already in flight: its response would otherwise
    // still look current and would draw the outlines on a map where the layer
    // is now off — and nothing would ever remove them.
    reqId.current += 1
    clearAll()
  }, [map, enabled])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map || !enabled) return
    let timer: number

    const kindsForZoom = (zoom: number): string[] => {
      let kinds: string[] = []
      for (const band of KINDS_BY_ZOOM) {
        if (zoom < band.minZoom) continue
        if (band.maxZoom !== null && zoom > band.maxZoom) continue
        kinds = kinds.concat(band.kinds)
      }
      return kinds
    }

    const draw = (outlines: GeoBoundary[]) => {
      const next = new Set<string>()
      for (const b of outlines) {
        next.add(b.uid)
        if (polygons.current.has(b.uid)) continue
        const color = colorForKind(b.kind, b.source)
        const made: google.maps.Polygon[] = []
        for (const polygon of polygonsOf(b.geometry)) {
          const paths = polygon.map((ring) => toPath(ring))
          if (!paths.length) continue
          const poly = new window.google.maps.Polygon({
            paths,
            strokeColor: color,
            strokeOpacity: 0.9,
            strokeWeight: 1.5,
            fillColor: color,
            fillOpacity: 0.08,
            clickable: true,
            zIndex: 20,
          })
          poly.setMap(map)
          poly.addListener('click', () => {
            const centroid = centroidOf(b)
            select.current({
              id: `geo-${b.uid}`,
              kind: 'geo',
              name: b.name,
              kicker: label.current(`geo.kind.${b.kind}`, b.kind),
              color,
              lat: centroid.lat,
              lng: centroid.lng,
              geo: {
                uid: b.uid,
                kind: b.kind,
                source: b.source,
                license: b.license ?? null,
                sourceUrl: b.source_url ?? null,
                areaKm2: b.area_km2 ?? null,
              },
            })
          })
          made.push(poly)
        }
        polygons.current.set(b.uid, made)
      }
      // Drop the outlines that are no longer in view.
      for (const [uid, list] of polygons.current) {
        if (next.has(uid)) continue
        for (const p of list) p.setMap(null)
        polygons.current.delete(uid)
      }
    }

    const fetchOutlines = () => {
      const b = map.getBounds()
      if (!b) return
      const zoom = map.getZoom() ?? 0
      const kinds = kindsForZoom(zoom)
      if (!kinds.length) return
      const ne = b.getNorthEast(), sw = b.getSouthWest()
      const bbox = `${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`
      const id = ++reqId.current
      geoApi.boundaries({ bbox, kind: kinds, limit: OUTLINE_CAP }).then((res) => {
        if (id !== reqId.current || !map) return
        if (res.truncated) {
          // The answer was cut short — the client says so rather than
          // silently drawing a map with holes in it.
          console.warn(
            `whereq: the administrative areas were truncated — ${res.items.length} of ${res.total}`)
        }
        draw(res.items)
      }).catch(() => { /* the map still works without the outlines */ })
    }

    const onIdle = () => { window.clearTimeout(timer); timer = window.setTimeout(fetchOutlines, 300) }
    const listener = map.addListener('idle', onIdle)
    fetchOutlines()
    return () => {
      window.clearTimeout(timer); listener.remove()
    }
  }, [map, enabled, onSelect])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => {
    for (const [, list] of polygons.current) for (const p of list) p.setMap(null)
    polygons.current.clear()
  }, [])

  return null
}
