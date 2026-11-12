// Advanced markers — the modern replacement for the deprecated
// `google.maps.Marker` (deprecated since February 2024).
//
// Three things change with the advanced marker model:
//
// - the content is a **DOM element**, not an icon url;
// - the click event is **`gmp-click`**, and the marker has to be asked to be
//   clickable (`gmpClickable: true` — it defaults to false, so a pin that
//   ignores clicks is the default state);
// - the marker anchors on its content's **bottom-centre**, where the legacy
//   symbol was centred on its point.
//
// The clusterer (`@googlemaps/markerclusterer`) supports both marker types.

import { idealText } from './popupCard'

/**
 * Advanced markers anchor on their content's bottom-centre by default; the
 * legacy symbol was centred on its point, so both offsets are pulled to the
 * middle (-50% of the content's width and height).
 */
export const ANCHOR_CENTER = { anchorLeft: '-50%', anchorTop: '-50%' } as const

/**
 * The clusterer attaches its cluster-click listener with
 * `marker.addListener('gmp-click', …)`, and the Maps API warns about
 * `addListener` on an advanced marker — it wants `addEventListener` with
 * 'gmp-' events. The marker is ours, so we point that one call at the modern
 * API instead of patching the library.
 */
export function withModernListener(mk: google.maps.marker.AdvancedMarkerElement) {
  mk.addListener = ((eventName: string, handler: Function): google.maps.MapsEventListener => {
    const listener = handler as unknown as EventListener
    mk.addEventListener(eventName, listener)
    return { remove: () => mk.removeEventListener(eventName, listener) }
  }) as typeof mk.addListener
  return mk
}

/**
 * The DOM content of an advanced marker that draws an icon we already have as
 * a prepared svg (the same picture the legacy marker showed).
 */
export function iconContent(url: string, width: number, height = width): HTMLImageElement {
  const img = document.createElement('img')
  img.src = url
  img.width = width
  img.height = height
  img.style.display = 'block'
  img.style.cursor = 'pointer'
  // An <img> is natively draggable; dragging it inside the map would drag a
  // ghost image instead of panning the map.
  img.draggable = false
  return img
}

/**
 * A cluster bubble: the count on the cluster's own bubble. The legacy
 * renderer drew this as an icon plus a label; as a DOM element it is the
 * bubble image with the count centred on it.
 */
export function clusterContent(
  count: number,
  color: string,
  iconUrl: string,
  size: number,
): HTMLElement {
  const el = document.createElement('div')
  el.style.width = `${size}px`
  el.style.height = `${size}px`
  el.style.backgroundImage = `url("${iconUrl}")`
  el.style.backgroundSize = '100% 100%'
  el.style.backgroundRepeat = 'no-repeat'
  el.style.display = 'flex'
  el.style.alignItems = 'center'
  el.style.justifyContent = 'center'
  el.style.fontFamily = 'var(--font-display, system-ui, sans-serif)'
  el.style.fontWeight = '700'
  el.style.fontSize = count < 100 ? '12px' : '11px'
  el.style.color = idealText(color)
  el.style.cursor = 'pointer'
  el.style.userSelect = 'none'
  el.textContent = String(count)
  return el
}
