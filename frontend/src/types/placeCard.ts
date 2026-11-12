/** The user's own card — a customised view of a place. */

export type PlaceCardKind = 'business' | 'person'

export interface PlaceCardDTO {
  id: number
  user_id: number
  name: string
  description: string | null
  kind: PlaceCardKind
  /** The business card's label ("food", "coffee", "clinic", …). */
  category: string | null
  latitude: number
  longitude: number
  address: string | null
  city: string | null
  country: string | null
  /** The radius of the aggregation under the card, in kilometres. */
  radius_km: number
  /** The categories the aggregation is filtered by. Empty = every category. */
  categories: string[]
  logo_url: string | null
  accent: string | null
  status: string
  publish_token: string | null
  published_at: string | null
  report_count: number
  view_count: number
  created_at: string
  updated_at: string
}

/** What the user may write. */
export interface PlaceCardInput {
  name: string
  description?: string | null
  kind: PlaceCardKind
  category?: string | null
  latitude: number
  longitude: number
  address?: string | null
  city?: string | null
  country?: string | null
  radius_km: number
  categories: string[]
  logo_url?: string | null
  accent?: string | null
}
