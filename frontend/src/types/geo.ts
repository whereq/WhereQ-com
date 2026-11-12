// Administrative geography — the areas that contain the places.
//
// A second vocabulary of place: provinces, regions, municipalities, cities,
// towns, wards and neighbourhoods, with real outlines. Two vocabularies live
// side by side (OpenStreetMap and geoBoundaries) and are never merged, so
// every row carries its `source` — and its `license`, because both are open
// data that may only be redistributed with attribution.

export interface GeoConcept {
  kind: string
  name: string
  name_cn?: string | null
  description?: string | null
  description_cn?: string | null
  /** Broadest first: 0 = country, 19 = unclassified. */
  rank: number
  /** How many of this kind *we* hold. */
  places: number
  /** The feed's own count for the whole dataset. */
  upstream_places: number
}

export interface GeoPlace {
  uid: string
  kind: string
  name: string
  name_en?: string | null
  name_zh?: string | null
  name_local?: string | null
  official_name?: string | null
  source: string
  source_url?: string | null
  license?: string | null
  country_code?: string | null
  province_code?: string | null
  population?: number | null
  area_km2?: number | null
  centroid_lon?: number | null
  centroid_lat?: number | null
  has_boundary: boolean
}

/**
 * A GeoJSON geometry.
 *
 * A Polygon is rings of points; a MultiPolygon is polygons of rings of
 * points. The union is discriminated on `type` so the layer never has to
 * cast its way through the geometry.
 */
export type GeoGeometry =
  | { type: 'Polygon'; coordinates: number[][][] }
  | { type: 'MultiPolygon'; coordinates: number[][][][] }

export interface GeoBoundary {
  uid: string
  name: string
  kind: string
  source: string
  license?: string | null
  source_url?: string | null
  geometry: GeoGeometry
  /** How much the outline was simplified, in metres (0 = full resolution). */
  simplified_m: number
  area_km2?: number | null
  /** Where the place is — the feed's own centroid. */
  centroid_lon?: number | null
  centroid_lat?: number | null
}

/** One hit of the containment stack. */
export interface GeoAtPlace {
  uid: string
  kind: string
  name: string
  source: string
  license?: string | null
  centroid_lon?: number | null
  centroid_lat?: number | null
}

export interface GeoAtResponse {
  lat: number
  lng: number
  /** Broadest first: country → province → region → city → ward → neighbourhood. */
  places: GeoAtPlace[]
}
