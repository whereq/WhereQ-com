// The category vocabulary of the nearby search.
//
// The chips reuse the labels the sidebar already uses (`quick.*`, `ess.*`,
// `legend.*`) so the same thing is not called two different names, and they
// take their colours from the map's own marker styles — the nearby list and
// the map markers must agree on what a "coffee" looks like.

import { POI_STYLE } from '@/components/map/placeMarkers'
import { CATEGORY_COLORS, LOCAL_CLUSTER_COLOR } from '@/components/map/localMarkers'

export interface NearbyCategory {
  id: string
  /** The i18n key for the chip label. */
  labelKey: string
  color: string
}

/**
 * The categories the nearby search can filter by.
 *
 * The order matches the backend's vocabulary (see `app/api/routes/nearby.py`):
 * the POI categories, the local essentials, then the three other tables.
 */
export const NEARBY_CATEGORIES: NearbyCategory[] = [
  { id: 'food', labelKey: 'quick.food', color: POI_STYLE.food.color },
  { id: 'coffee', labelKey: 'quick.coffee', color: POI_STYLE.coffee.color },
  { id: 'fuel', labelKey: 'quick.fuel', color: POI_STYLE.fuel.color },
  { id: 'parking', labelKey: 'quick.parking', color: POI_STYLE.parking.color },
  { id: 'stays', labelKey: 'quick.stays', color: POI_STYLE.stays.color },
  { id: 'pharmacy', labelKey: 'ess.pharmacies', color: POI_STYLE.pharmacy.color },
  { id: 'clinic', labelKey: 'ess.clinics', color: POI_STYLE.clinic.color },
  { id: 'library', labelKey: 'ess.libraries', color: POI_STYLE.library.color },
  { id: 'plaza', labelKey: 'ess.plazas', color: POI_STYLE.plaza.color },
  { id: 'memorial', labelKey: 'legend.memorial', color: 'var(--memorial)' },
  { id: 'school', labelKey: 'ess.schools', color: '#E6B450' },
  { id: 'news', labelKey: 'nearby.news', color: LOCAL_CLUSTER_COLOR },
  { id: 'alerts', labelKey: 'nearby.alerts', color: CATEGORY_COLORS.accident },
]

export const NEARBY_CATEGORY_IDS: string[] = NEARBY_CATEGORIES.map(c => c.id)

/** The radius choices, in kilometres. */
export const NEARBY_RADII_KM: number[] = [0.5, 1, 2, 5, 10]

export const DEFAULT_RADIUS_KM = 5

/** "500 m" / "2 km" */
export function formatRadius(km: number): string {
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km} km`
}

/**
 * Toggle one category in a selection.
 *
 * The chip model is "on = shown", and the **empty** selection means every
 * category — so the last category cannot be switched off (there is no
 * "nothing at all" state, and empty would silently mean "everything").
 *
 * Returns the next selection, or `null` when the toggle is not allowed —
 * which is what happens to the last one.
 */
export function toggleCategorySelection(
  selected: string[],
  id: string,
  allIds: string[] = NEARBY_CATEGORY_IDS,
): string[] | null {
  const current = selected.length ? selected : allIds
  const next = new Set(current)
  if (next.has(id)) {
    next.delete(id)
    if (next.size === 0) return null
  } else {
    next.add(id)
  }
  // An empty selection *is* every category, so it is stored as empty.
  return next.size === allIds.length ? [] : Array.from(next)
}
