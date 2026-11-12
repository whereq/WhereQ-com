import { useEffect, useRef } from 'react'
import { useMap } from '@vis.gl/react-google-maps'
import { useMapContext } from '@/contexts/MapContext'
import { geoApi } from '@/lib/geoApi'
import type { GeoBoundary } from '@/types/geo'
import type { MapSelection } from '@/types/selection'
import { boundsOf, colorForKind, fitPadding, polygonsOf, toPath } from './geoStyles'

/**
 * The focused area — the one administrative boundary the user asked to see.
 *
 * The card of a place answers "contained in" with a stack of areas, and the
 * question that follows is always the same: *"show me the one I am in."*
 * This layer answers it. The outline is fetched by uid (the whole feed is
 * already in our database, so this is one cheap request), drawn in the kind's
 * own colour — the same colour the viewport layer uses, so the focused area
 * looks like the same area — and the map is fitted to it.
 *
 * The layer is deliberately *not* the viewport layer. That one draws every
 * area in view, which is the right thing when the user wants to see the
 * administrative fabric; this one draws one area, which is the right thing
 * when the user has just been told "you are in Kensington-Chinatown" and wants
 * to see where that is.
 */
export function GeoFocusLayer({
  onSelect,
}: {
  onSelect: (sel: MapSelection) => void
}) {
  const map = useMap()
  const { geoFocus, clearGeoFocus } = useMapContext()
  const polygons = useRef<google.maps.Polygon[]>([])
  const select = useRef(onSelect)
  select.current = onSelect

  const clearAll = () => {
    for (const p of polygons.current) p.setMap(null)
    polygons.current = []
  }

  // The outline goes away when the layer unmounts.
  useEffect(() => () => { clearAll() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map || !geoFocus) return
    let cancelled = false

    const draw = (b: GeoBoundary) => {
      if (cancelled) return
      clearAll()
      const color = colorForKind(b.kind, b.source)
      for (const polygon of polygonsOf(b.geometry)) {
        const paths = polygon.map((ring) => toPath(ring))
        if (!paths.length) continue
        // A halo underneath: a wide, translucent stroke of the same colour.
        // Without it the 3px outline is easy to lose against the map, and in
        // the dark theme the 16% fill is almost invisible.
        const halo = new window.google.maps.Polygon({
          paths,
          strokeColor: color,
          strokeOpacity: 0.28,
          strokeWeight: 9,
          fillOpacity: 0,
          clickable: false,
          zIndex: 39,
        })
        halo.setMap(map)
        polygons.current.push(halo)

        const poly = new window.google.maps.Polygon({
          paths,
          strokeColor: color,
          strokeOpacity: 1,
          strokeWeight: 3,
          fillColor: color,
          fillOpacity: 0.3,
          clickable: true,
          zIndex: 40,
        })
        poly.setMap(map)
        poly.addListener('click', () => {
          select.current({
            id: `geo-${b.uid}`,
            kind: 'geo',
            name: b.name,
            kicker: b.kind,
            color,
            lat: b.centroid_lat ?? 0,
            lng: b.centroid_lon ?? 0,
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
        polygons.current.push(poly)
      }
      // Fit the shape in view — a neighbourhood must be seen at its own size,
      // not at the size of whatever the map happened to be showing — and in
      // the part of the map the card is not sitting on.
      const bounds = boundsOf(b.geometry)
      if (bounds && !bounds.isEmpty()) {
        map.fitBounds(bounds, fitPadding(map, document.querySelector('.search-modal-place')))
      }
    }

    geoApi.boundary(geoFocus.uid).then((b) => {
      if (cancelled) return
      draw(b)
    }).catch(() => {
      // The area has no outline in the feed — say so rather than leave the
      // user wondering why nothing appeared.
      clearGeoFocus()
    })

    return () => { cancelled = true }
  }, [map, geoFocus, clearGeoFocus])

  return null
}
