// What the user picked on the map.
//
// A POI, a school, a hazard, a news item, a friend, a memorial or a searched
// address — they all become one shape, so every marker on the map opens the
// same presentation (the search modal, scoped to that place).

import type { PopupPrices } from '@/components/map/popupCard'

export type SelectionKind =
  | 'poi'
  | 'school'
  | 'hazard'
  | 'local'
  | 'friend'
  | 'me'
  | 'memorial'
  | 'address'
  | 'geo'

/** An administrative area picked on the map (a ward, a city, a neighbourhood). */
export interface GeoSelectionInfo {
  uid: string
  kind: string
  /** Which vocabulary: "osm" or "geoboundaries". */
  source: string
  /** The licence the data is published under — the attribution we owe. */
  license?: string | null
  sourceUrl?: string | null
  areaKm2?: number | null
}

export interface MapSelection {
  /** Stable id — "place-12", "school-4", "local-88", "search-…" … */
  id: string
  kind: SelectionKind
  /** The display name. */
  name: string
  /** The coloured header label ("Pharmacy", "School", "Accident" …). */
  kicker: string
  /** The second line under the title. */
  subtitle?: string
  /** The accent colour — from the map's own palette. */
  color: string
  lat: number
  lng: number
  /** Our place id — the card can load the full record and save it. */
  placeId?: number
  /** The POI category (food, coffee, gas, school …). */
  category?: string
  address?: string | null
  city?: string | null
  description?: string | null
  phone?: string | null
  website?: string | null
  hours?: string | null
  /** The fuel-station price panel (licensed — signed-in users only). */
  prices?: PopupPrices | null
  /** A paragraph: a news summary, a story. */
  body?: string | null
  image?: string | null
  /** "2 h ago" — when it happened. */
  when?: string | null
  /** Where it came from (a news source). */
  source?: string | null
  /** The link to the original article. */
  sourceUrl?: string | null
  /** Hazard: how bad it is and how many people confirmed it. */
  severity?: string
  confirmations?: number
  createdAt?: string
  /** School: the level, the board and the score. */
  schoolType?: string | null
  boardType?: string | null
  score?: number | null
  /** True for the pin a search drops on the map. */
  isSearchPin?: boolean
  /** The administrative area this selection is (a picked polygon). */
  geo?: GeoSelectionInfo
}
