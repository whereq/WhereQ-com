// The unified nearby search — everything around the map centre, in one list.
// Mirrors the backend's NearbyItem / NearbyResponse.

/** One thing near the centre. `type` says which table it came from. */
export interface NearbyItem {
  id: string
  type: 'place' | 'local' | 'school' | 'hazard'
  /** The filter key the UI groups by (food, coffee, school, news, …). */
  category: string
  subcategory?: string | null
  name: string
  meta?: string | null
  lat: number
  lng: number
  distance_m: number
  /** The live fuel price — signed-in users only (the prices are licensed). */
  price?: number | null
  currency?: string | null
  observed_at?: string | null
  url?: string | null
  image_url?: string | null
  when?: string | null
}

export interface NearbyResponse {
  items: NearbyItem[]
  /** How many items each category contributed — the badges on the chips. */
  counts: Record<string, number>
  total: number
  radius_m: number
  center: { lat: number; lng: number }
  /** The categories that were applied. */
  categories: string[]
}

/** The account-scoped settings (the nearby radius and category selection). */
export interface UserSettingsDTO {
  radius_km: number
  categories: string[]
  updated_at?: string | null
}
