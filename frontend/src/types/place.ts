/** Lightweight POI pin from GET /places/map. */
export interface PlacePin {
  id: number
  /** Display name. */
  title: string
  lat: number
  lng: number
  /** essentials kind (pharmacy/clinic/library/plaza) or "poi" for quick categories. */
  kind: string
  /** POI category (food/coffee/fuel/parking/stays) when kind === "poi". */
  category: string
  sub: string | null
}

/** Viewport counts: { pharmacy: n, clinic: n, ..., "cat:food": n }. */
export type PlaceCounts = Record<string, number>
