// Category → marker color + label for the local-content layer.
// Palette intentionally avoids the pink family to fit the app theme.

export const CATEGORY_COLORS: Record<string, string> = {
  accident: '#F97316',       // orange
  crime: '#DC2626',          // red
  fire: '#EA580C',           // deep orange
  weather: '#38BDF8',        // sky
  transportation: '#FBBF24', // amber
  construction: '#F59E0B',   // amber-orange
  festival: '#818CF8',       // indigo
  event: '#6366F1',          // indigo-violet
  business: '#2DD4BF',       // teal
  education: '#5BA5FF',      // blue
  government: '#94A3B8',     // slate
  community: '#4ADE80',      // green
  health: '#22D3EE',         // cyan
  other: '#9CA3AF',          // gray
}

export const CATEGORY_LABELS: Record<string, string> = {
  accident: 'Accident', crime: 'Crime', fire: 'Fire', weather: 'Weather',
  transportation: 'Transportation', construction: 'Construction', festival: 'Festival',
  event: 'Event', business: 'Business', education: 'Education', government: 'Government',
  community: 'Community', health: 'Health', other: 'Local',
}

export function categoryColor(category: string): string {
  return CATEGORY_COLORS[category] ?? CATEGORY_COLORS.other
}

/** Border color for cluster bubbles — a single on-brand "local" hue so groups
 *  read as one family regardless of the categories inside them. */
export const LOCAL_CLUSTER_COLOR = '#7DD3FC'

function svgDataUrl(svg: string): string {
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg)
}

/** Pixel size + center anchor of a local-content marker icon. */
export const LOCAL_PIN_SIZE = 34

// Inner glyph by content type (centered ~17,17) so News / Events / Stories /
// Topics read distinctly while sharing the "local content" chip family.
function typeGlyph(type: string): string {
  switch (type) {
    case 'event':  // calendar
      return `<rect x="11.5" y="12" width="11" height="9" rx="1.5" fill="#FFFFFF"/>`
        + `<rect x="11.5" y="12" width="11" height="3" rx="1.5" fill="#0A0E13" fill-opacity="0.55"/>`
        + `<rect x="13.5" y="10.6" width="1.6" height="3" rx="0.6" fill="#FFFFFF"/>`
        + `<rect x="18.9" y="10.6" width="1.6" height="3" rx="0.6" fill="#FFFFFF"/>`
    case 'story':  // bookmark
      return `<path d="M13 11 H21 V22 L17 19 L13 22 Z" fill="#FFFFFF"/>`
    case 'topic':  // hash
      return `<text x="17" y="20.5" text-anchor="middle" font-size="12" font-weight="800"`
        + ` fill="#FFFFFF" font-family="system-ui,sans-serif">#</text>`
    default:       // news — solid square
      return `<rect x="14" y="14" width="6" height="6" rx="2" fill="#FFFFFF" fill-opacity="0.95"/>`
  }
}

/**
 * Distinctive, high-visibility local-content marker: a rounded-square "chip"
 * (clearly different from the round Google POI dots and the app's teardrop
 * pins) with a category-colored core, a white ring, a constant bright "local"
 * sky halo, a drop shadow, and a per-type inner glyph. 34×34, center anchor.
 */
export function localPinIconUrl(color: string, type = 'news'): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="34" height="34" viewBox="0 0 34 34">`
    + `<rect x="8" y="9" width="20" height="20" rx="7" fill="#06090D" opacity="0.5"/>`
    + `<rect x="7" y="7" width="20" height="20" rx="7" fill="${LOCAL_CLUSTER_COLOR}"/>`
    + `<rect x="9" y="9" width="16" height="16" rx="5" fill="${color}" stroke="#FFFFFF" stroke-width="2"/>`
    + typeGlyph(type)
    + `</svg>`
  return svgDataUrl(svg)
}

/** Cluster bubble: a larger rounded square (same shape language as the chips),
 *  SOLID-filled with the layer color (so News / POIs / Schools clusters are
 *  easy to tell apart) + white ring + shadow. Count is the Marker label. */
export function clusterIconUrl(size: number, color = LOCAL_CLUSTER_COLOR): string {
  const r = (size - 6) / 3.4
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">`
    + `<rect x="4" y="5" width="${size - 8}" height="${size - 8}" rx="${r}" fill="#06090D" opacity="0.4"/>`
    + `<rect x="3" y="3" width="${size - 6}" height="${size - 6}" rx="${r}" fill="${color}" stroke="#FFFFFF" stroke-width="2.5"/>`
    + `</svg>`
  return svgDataUrl(svg)
}

/** Pixel size of a cluster bubble for a given member count. */
export function clusterSize(count: number): number {
  return count < 10 ? 36 : count < 50 ? 44 : count < 200 ? 52 : 60
}

export function escapeHtml(s: string | null | undefined): string {
  if (!s) return ''
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string
  ))
}

export function formatWhen(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

