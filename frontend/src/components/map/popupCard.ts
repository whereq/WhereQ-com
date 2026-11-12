// The cluster pick-list card and the shared helpers of the map popups.
//
// The single-item card is React now (`components/search/PlaceCard.tsx`) — the
// one presentation every marker on the map opens. What is left here is the
// cluster pick-list (a map affordance for choosing between overlapping
// markers) and the helpers it shares.

/** One line of the price panel: "Regular" → "1.76". */
export interface PopupPriceItem { label: string; value: string }

/**
 * A highlighted price panel (the fuel-station prices).
 *
 * Rendered as its own tinted block instead of a plain row, so the numbers
 * line up in a column and read as the headline of the card.
 */
export interface PopupPrices {
  items: PopupPriceItem[]
  /** The currency the values are quoted in, e.g. "CAD/L". */
  unit?: string | null
  /** A freshness note, e.g. "Updated 7h ago". */
  note?: string | null
}

/** A cluster pick-list row. */
export interface ListItem { id: number; name: string; meta?: string; color: string }

export function escapeHtml(s: string | null | undefined): string {
  if (!s) return ''
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string
  ))
}

/** Dark or white text for legibility on a given background color. */
export function idealText(hex: string): string {
  const m = hex.replace('#', '')
  if (m.length < 6) return '#FFFFFF'
  const ch = (i: number) => parseInt(m.substring(i, i + 2), 16) / 255
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4))
  const L = 0.2126 * lin(ch(0)) + 0.7152 * lin(ch(2)) + 0.0722 * lin(ch(4))
  return L > 0.55 ? '#0A0E13' : '#FFFFFF'
}

// Shared ✕ — inline onclick dispatch so it survives setContent re-renders;
// each layer listens for `whereq:popup-close` and closes its InfoWindow.
const CLOSE_BTN = `<button aria-label="Close" onclick="window.dispatchEvent(new CustomEvent('whereq:popup-close'))" `
  + `style="position:absolute;top:7px;right:8px;width:22px;height:22px;border:0;border-radius:50%;`
  + `background:rgba(0,0,0,.35);color:#fff;font-size:13px;line-height:1;display:flex;align-items:center;`
  + `justify-content:center;cursor:pointer;z-index:3">✕</button>`

/** Full-bleed colored header bar with auto-contrast text. */
function headerBar(accent: string, kicker: string, roundTop = true): string {
  return `<div style="background:${accent};color:${idealText(accent)};padding:10px 44px 10px 14px;`
    + `font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;`
    + `${roundTop ? 'border-radius:8px 8px 0 0;' : ''}">${escapeHtml(kicker)}</div>`
}

/** Cluster pick-list, sharing the single card's header (colored to match the
 *  cluster). Rows carry `data-pin` for the layer to wire focus on click. */
export function popupListCard(accent: string, title: string, items: ListItem[]): string {
  const rows = items.map((it) =>
    `<button data-pin="${it.id}" class="wq-list-row" style="display:flex;gap:9px;align-items:flex-start;`
    + `width:100%;background:none;border:0;padding:8px 6px;border-radius:6px;cursor:pointer;text-align:left">`
    + `<span style="width:10px;height:10px;border-radius:50%;background:${it.color};margin-top:3px;flex:none"></span>`
    + `<span style="flex:1;min-width:0"><span style="display:block;font-size:13.5px;font-weight:600;line-height:1.3;color:#0A0E13">${escapeHtml(it.name)}</span>`
    + `${it.meta ? `<span style="display:block;font-size:11.5px;color:#475569;margin-top:1px">${escapeHtml(it.meta)}</span>` : ''}</span></button>`,
  ).join('')
  return `<div style="position:relative;width:264px;overflow:hidden;border-radius:8px;font-family:var(--font-sans,system-ui,sans-serif)">`
    + CLOSE_BTN + headerBar(accent, title)
    + `<div style="padding:8px 10px 10px;max-height:280px;overflow-y:auto">${rows}</div>`
    + `<style>.wq-list-row:hover{background:#EEF2F7}</style></div>`
}
