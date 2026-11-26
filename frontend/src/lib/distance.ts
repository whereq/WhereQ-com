/**
 * Great-circle distance between two points.
 *
 * One implementation, written once: the sidebar and the neighbourhood hook
 * each had their own copy of this, and the social page needed a third.
 *
 * The model is a **sphere** with r = 6,371,000 m — the same constant the
 * backend's Python haversine uses (`backend/app/api/routes/nearby.py`). It is
 * a display distance, not a radius filter: the filters use the WGS84
 * spheroid (PostGIS `ST_DWithin` on `geography`), so the two differ by a few
 * metres at city scale.
 */
export function metersBetween(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number },
): number {
  const R = 6371000
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLng = ((b.lng - a.lng) * Math.PI) / 180
  const la1 = (a.lat * Math.PI) / 180
  const la2 = (b.lat * Math.PI) / 180
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

/** A distance as "820m" or "3.4km". */
export function fmtDist(m: number): string {
  return m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`
}
