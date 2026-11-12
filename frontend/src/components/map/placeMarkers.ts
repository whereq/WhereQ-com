// Marker styling + popup for the viewport POI layer (Local Essentials +
// Quick Categories). Keyed by kind (essentials) or POI category.
import type { PlacePin } from '@/types/place'
import type { PopupPriceItem } from './popupCard'

interface PoiStyle { color: string; glyph: string; label: string; icon?: string }

/**
 * A fuel pump, drawn as SVG (a 24×24 fragment scaled into the marker).
 * `{bg}` is replaced with the marker colour, so the display window reads as a
 * hole in the white pump body.
 */
const FUEL_PUMP_ICON = `
  <rect x="3" y="2" width="9" height="18" rx="1.6" fill="#FFFFFF"/>
  <rect x="5.2" y="4.4" width="4.6" height="4.8" rx="0.9" fill="{bg}"/>
  <rect x="1.4" y="18.4" width="12.2" height="2.8" rx="1.4" fill="#FFFFFF"/>
  <path d="M13.4 4h2.6a2.2 2.2 0 0 1 2.2 2.2v9.4" fill="none" stroke="#FFFFFF" stroke-width="2.4" stroke-linecap="round"/>
  <rect x="16.6" y="15.6" width="3.2" height="4.4" rx="1.2" fill="#FFFFFF"/>`

export const POI_STYLE: Record<string, PoiStyle> = {
  // Local Essentials (by kind)
  pharmacy: { color: '#34D399', glyph: '+', label: 'Pharmacy' },
  clinic: { color: '#F87171', glyph: '+', label: 'Walk-in clinic' },
  library: { color: '#818CF8', glyph: 'L', label: 'Library' },
  plaza: { color: '#FB923C', glyph: '◇', label: 'Plaza' },
  // Quick Categories (by POI category)
  food: { color: '#FF7A4D', glyph: 'F', label: 'Food' },
  coffee: { color: '#A0763C', glyph: 'C', label: 'Coffee' },
  fuel: { color: '#4ADE80', glyph: 'G', label: 'Fuel', icon: FUEL_PUMP_ICON },
  gas: { color: '#F59E0B', glyph: '$', label: 'Gas station', icon: FUEL_PUMP_ICON },
  parking: { color: '#5BA5FF', glyph: 'P', label: 'Parking' },
  stays: { color: '#A78BFA', glyph: 'H', label: 'Stays' },
}

const FALLBACK: PoiStyle = { color: '#9CA3AF', glyph: '•', label: 'Place' }

/** Cluster bubble color for the POI layer (distinct from the News sky clusters). */
export const POI_CLUSTER_COLOR = '#4ADE80'

export function poiStyle(pin: Pick<PlacePin, 'kind' | 'category'>): PoiStyle {
  return (pin.kind === 'poi' ? POI_STYLE[pin.category] : POI_STYLE[pin.kind]) ?? FALLBACK
}

function svgDataUrl(svg: string): string {
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg)
}

/** Pixel size + center anchor of a POI marker icon. */
export const POI_PIN_SIZE = 28

/** Colored, white-ringed circular marker with a glyph (or an icon) + shadow. */
export function poiIconUrl(color: string, glyph: string, icon?: string): string {
  // An icon is drawn as SVG (a 24×24 fragment scaled into the disc); the
  // marker colour fills the gaps so the glyph reads as a cut-out.
  const inner = icon
    ? `<g transform="translate(7.4,5.4) scale(0.56)">${icon.replace(/\{bg\}/g, color)}</g>`
    : `<text x="14" y="17" text-anchor="middle" font-size="12" font-weight="700" fill="#FFFFFF"`
      + ` font-family="system-ui,sans-serif">${glyph}</text>`
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">`
    + `<circle cx="14" cy="15" r="10" fill="#06090D" opacity="0.45"/>`
    + `<circle cx="14" cy="13" r="10" fill="${color}" stroke="#FFFFFF" stroke-width="2"/>`
    + inner
    + `</svg>`
  return svgDataUrl(svg)
}

/** Human labels for the fuel products whereq.cloud quotes. */
const PRODUCT_LABELS: Record<string, string> = {
  regular: 'Regular',
  midgrade: 'Midgrade',
  premium: 'Premium',
  diesel: 'Diesel',
  e85: 'E85',
  lpg: 'LPG',
  heating: 'Heating oil',
}

/**
 * Whereq.cloud fuel prices { product: { price, observed_at } } → the rows of
 * the price panel: one line per product, common products first.
 */
export function formatPriceItems(prices: unknown): PopupPriceItem[] {
  if (!prices || typeof prices !== 'object') return []
  const order = ['regular', 'midgrade', 'premium', 'diesel', 'e85']
  return Object.entries(prices as Record<string, { price?: unknown }>)
    .filter(([, v]) => v && typeof v.price === 'number')
    .map(([prod, v]) => ({ prod, price: v.price as number }))
    .sort((a, b) => (order.indexOf(a.prod) + 1 || 99) - (order.indexOf(b.prod) + 1 || 99))
    .map(({ prod, price }) => ({
      label: PRODUCT_LABELS[prod] ?? (prod.charAt(0).toUpperCase() + prod.slice(1)),
      value: price.toFixed(2),
    }))
}

/** "Updated 2h ago" for a price observation timestamp. */
export function formatFreshness(observedAt: unknown): string | undefined {
  if (typeof observedAt !== 'string') return undefined
  const ts = Date.parse(observedAt)
  if (Number.isNaN(ts)) return undefined
  const mins = Math.max(0, Math.round((Date.now() - ts) / 60000))
  if (mins < 1) return 'Updated just now'
  if (mins < 60) return `Updated ${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `Updated ${hours}h ago`
  return `Updated ${Math.round(hours / 24)}d ago`
}

