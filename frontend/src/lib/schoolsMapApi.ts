import { api } from './api'
import type { GeoGeometry } from '@/types/geo'

/** Lightweight school pin from GET /schools/map (main-map layer). */
export interface SchoolMapPin {
  id: number
  name: string
  lat: number
  lng: number
  type: string | null
  board_type: string | null
  hs_score: number | null
  has_boundary: boolean
}

/**
 * The catchment outline of one school.
 *
 * A school is not a point: it serves an *area*. The map needs that shape, so
 * it has its own endpoint — the geometry without the rest of the school
 * record. **Gated**: the catchment polygons are the licensed board data, so a
 * signed-in user is required (an anonymous call answers 401).
 */
export interface SchoolBoundary {
  school_id: number
  name: string
  geometry: GeoGeometry | null
  polygon_count: number
  point_count: number
}

export const schoolsMapApi = {
  map: (bbox: string, limit = 3000) =>
    api.get<SchoolMapPin[]>(`/schools/map?bbox=${encodeURIComponent(bbox)}&limit=${limit}`),
  /** Accurate viewport school count via the paginated list's `total`. */
  count: async (bbox: string): Promise<number> =>
    (await api.get<{ total: number }>(`/schools?bbox=${encodeURIComponent(bbox)}&page_size=1`)).total,
  /** The catchment outline (GeoJSON MultiPolygon). Signed-in users only. */
  boundary: (id: number) => api.get<SchoolBoundary>(`/schools/${id}/boundary`),
}
