import { useEffect, useRef } from 'react'
import { useMap } from '@vis.gl/react-google-maps'
import { useMapContext } from '@/contexts/MapContext'
import { useAuth } from '@/contexts/AuthContext'
import { schoolsMapApi } from '@/lib/schoolsMapApi'
import { boundsOf, fitPadding, polygonsOf, toPath } from './geoStyles'

/**
 * The catchment outline of the picked school.
 *
 * A school is not a point — it serves an *area*, and that area is what the
 * user is looking for when they pick one. This layer fetches that area and
 * draws it: the same orange the standalone schools app uses, so the shape
 * looks the same in both apps of the whereq universe, and the map is fitted
 * to it so the whole catchment is on screen at once.
 *
 * The fetch lives here, not in the card, for one reason: the card is closed
 * as soon as the user wants to *look* at the shape, so the outline must
 * outlive it. The layer lives with the map.
 *
 * The catchment polygons are the school board's licensed data, so they are
 * gated — an anonymous visitor gets nothing drawn and the card offers the
 * sign-in instead.
 */
const BOUNDARY_COLOR = '#F97316'

/** The school behind a selection ("school-ycdsb/0158" → "ycdsb/0158"). */
function schoolUidOf(id: string | undefined, kind: string | undefined): string | null {
  if (!id || kind !== 'school') return null
  const uid = id.replace(/^school-/, '')
  return uid || null
}

export function SchoolBoundaryLayer() {
  const map = useMap()
  const { selection, schoolBoundary, requestSchoolBoundary, clearSchoolBoundary } = useMapContext()
  const { isAuthenticated } = useAuth()
  const polygons = useRef<google.maps.Polygon[]>([])

  const clearAll = () => {
    for (const p of polygons.current) p.setMap(null)
    polygons.current = []
  }

  // The outline goes away when the layer unmounts.
  useEffect(() => () => { clearAll() }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // The shape of the picked school — fetched here, drawn below.
  useEffect(() => {
    const schoolUid = schoolUidOf(selection?.id, selection?.kind)
    if (schoolUid == null) {
      // Another kind of place — there is no catchment to draw.
      clearSchoolBoundary()
      return
    }
    if (!isAuthenticated) {
      // Gated data: the card offers the sign-in instead of drawing nothing.
      clearSchoolBoundary()
      return
    }
    // The previous school's shape goes now: the map must not show two
    // catchments while the new one loads.
    clearSchoolBoundary()
    let cancelled = false
    schoolsMapApi.boundary(schoolUid).then(b => {
      if (cancelled || !b.geometry) return
      requestSchoolBoundary({ schoolUid: b.school_uid, name: b.name, geometry: b.geometry })
    }).catch(() => {
      // No catchment for this school, or the session went away: nothing is
      // drawn, and the card shows the school without a catchment chip.
    })
    return () => { cancelled = true }
  }, [selection?.id, selection?.kind, isAuthenticated, requestSchoolBoundary, clearSchoolBoundary])

  // The drawing.
  useEffect(() => {
    if (!map) return
    clearAll()
    if (!schoolBoundary) return
    const { geometry } = schoolBoundary
    for (const polygon of polygonsOf(geometry)) {
      const paths = polygon.map((ring) => toPath(ring))
      if (!paths.length) continue
      // A halo under the outline, like the administrative-area layer: a 3px
      // line is easy to lose against the map, and the dark theme swallows it.
      const halo = new window.google.maps.Polygon({
        paths,
        strokeColor: BOUNDARY_COLOR,
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
        strokeColor: BOUNDARY_COLOR,
        strokeOpacity: 1,
        strokeWeight: 3,
        fillColor: BOUNDARY_COLOR,
        fillOpacity: 0.22,
        clickable: false,
        zIndex: 40,
      })
      poly.setMap(map)
      polygons.current.push(poly)
    }
    // Fit the catchment in view — a catchment must be seen at its own size —
    // and in the part of the map the card is not sitting on.
    const bounds = boundsOf(geometry)
    if (bounds && !bounds.isEmpty()) {
      map.fitBounds(bounds, fitPadding(map, document.querySelector('.search-modal-place')))
    }
  }, [map, schoolBoundary])

  return null
}
