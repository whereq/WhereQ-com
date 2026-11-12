// Colours + labels for the search result lists (the ⌘K modal and the
// sidebar's own search box).
//
// The colours come from the map's own marker styles (POI_STYLE) so a
// "coffee" result looks like a coffee marker. The app had four colour maps
// before this one; it must not grow a fifth.

import { POI_STYLE } from '@/components/map/placeMarkers'

export const KIND_COLORS: Record<string, string> = {
  address: 'var(--info)',
  poi: 'var(--accent)',
  memorial: 'var(--memorial)',
  school: '#E6B450',
  pharmacy: POI_STYLE.pharmacy.color,
  clinic: POI_STYLE.clinic.color,
  plaza: POI_STYLE.plaza.color,
  library: POI_STYLE.library.color,
  gas: POI_STYLE.gas.color,
  food: POI_STYLE.food.color,
  coffee: POI_STYLE.coffee.color,
  fuel: POI_STYLE.fuel.color,
  parking: POI_STYLE.parking.color,
  stays: POI_STYLE.stays.color,
}

/**
 * The palette's own hex values, for the places that need a real colour:
 * an SVG `fill` attribute does not resolve `var(--x)`, and the contrast
 * helper parses hex.
 */
const VAR_HEX: Record<string, string> = {
  'var(--info)': '#5BA5FF',
  'var(--accent)': '#4ADE80',
  'var(--success)': '#4ADE80',
  'var(--memorial)': '#B388FF',
  'var(--social)': '#FF8FB1',
  'var(--muted)': '#6A7689',
  'var(--warn)': '#FFB020',
  'var(--danger)': '#FF3B5C',
}

/** The hex behind a colour token (a CSS variable is resolved by hand). */
export function resolveColor(color: string): string {
  return VAR_HEX[color] ?? color
}

/** The dot colour of a search result — its category wins over its kind. */
export function resultColor(r: { kind: string; category?: string }): string {
  return (r.category ? KIND_COLORS[r.category] : undefined) ?? KIND_COLORS[r.kind] ?? 'var(--muted)'
}

/** "Food" / "Pharmacy" / "Memorial" — the label of a place row in a result list. */
export function placeLabel(p: { kind: string; category: string }): string {
  if (p.kind === 'poi') return POI_STYLE[p.category]?.label ?? 'Place'
  return p.kind.charAt(0).toUpperCase() + p.kind.slice(1)
}
