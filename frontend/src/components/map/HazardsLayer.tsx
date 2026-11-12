import { useEffect, useRef } from 'react'
import { useMap, useMapsLibrary } from '@vis.gl/react-google-maps'
import { hazardsApi } from '@/lib/hazardsApi'
import { iconContent, withModernListener } from './advancedMarkers'
import type { HazardPin } from '@/types/hazard'
import type { MapSelection } from '@/types/selection'

const SEVERITY_COLOR: Record<string, string> = { low: '#FBBF24', med: '#F59E0B', high: '#FF3B5C' }
const TYPE_LABEL: Record<string, string> = {
  accident: 'Accident', closure: 'Road closure', police: 'Police',
  weather: 'Weather', hazard: 'Hazard', other: 'Report',
}

function hazardIconUrl(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="26" viewBox="0 0 28 26">`
    + `<path d="M14 3 L26 23 L2 23 Z" fill="#06090D" opacity="0.4" transform="translate(0,1)"/>`
    + `<path d="M14 2 L26 22 L2 22 Z" fill="${color}" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round"/>`
    + `<text x="14" y="20" text-anchor="middle" font-size="13" font-weight="800" fill="#FFFFFF" font-family="system-ui,sans-serif">!</text>`
    + `</svg>`
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg)
}

/**
 * The legacy hazard marker was anchored at (14, 22) of the 28×26 canvas — the
 * triangle's **base**, not its centre. An advanced marker's anchor offsets are
 * measured from the content's top-left corner, so the same point is
 * `-14px / -22px`; the default anchor would be the bottom-centre (0, 26) and
 * would lift the base 4px off the location.
 */
const HAZARD_ANCHOR = { anchorLeft: '-14px', anchorTop: '-22px' } as const

function ago(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 60) return `${mins} min ago`
  const h = Math.round(mins / 60)
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`
}

/** Read layer for community hazard reports (clustered-free; reports are sparse). */
export function HazardsLayer({ enabled, onSelect }: { enabled: boolean; onSelect: (sel: MapSelection) => void }) {
  const map = useMap()
  // The marker library is loaded on demand; the advanced markers need it.
  const AdvancedMarkerElement = useMapsLibrary('marker')?.AdvancedMarkerElement
  const markers = useRef<Map<number, google.maps.marker.AdvancedMarkerElement>>(new Map())
  const reqId = useRef(0)

  const clearAll = () => {
    for (const [, mk] of markers.current) mk.map = null
    markers.current.clear()
  }

  useEffect(() => {
    if (!map || enabled) return
    clearAll()
  }, [map, enabled])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map || !enabled || !AdvancedMarkerElement) return
    let timer: number

    /** A picked pin → the card the map opens for it. */
    const selectPin = (h: HazardPin) => {
      onSelect({
        id: `hazard-${h.id}`,
        kind: 'hazard',
        name: h.title,
        kicker: TYPE_LABEL[h.type] ?? h.type,
        color: SEVERITY_COLOR[h.severity] ?? SEVERITY_COLOR.med,
        lat: h.lat,
        lng: h.lng,
        severity: h.severity,
        confirmations: h.confirmations,
        createdAt: h.created_at,
        when: ago(h.created_at),
      })
    }

    const fetchPins = () => {
      const b = map.getBounds()
      if (!b) return
      const ne = b.getNorthEast(), sw = b.getSouthWest()
      const bbox = `${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`
      const id = ++reqId.current
      hazardsApi.map(bbox).then((pins) => {
        if (id !== reqId.current || !map) return
        const next = new Set(pins.map((p) => p.id))
        for (const [pid, mk] of markers.current) {
          if (!next.has(pid)) { mk.map = null; markers.current.delete(pid) }
        }
        for (const h of pins) {
          if (markers.current.has(h.id)) continue
          const mk = withModernListener(new AdvancedMarkerElement({
            position: { lat: h.lat, lng: h.lng },
            map,
            content: iconContent(
              hazardIconUrl(SEVERITY_COLOR[h.severity] ?? SEVERITY_COLOR.med), 28, 26,
            ),
            title: h.title,
            zIndex: 5,
            // Advanced markers are not clickable unless asked to be.
            gmpClickable: true,
            ...HAZARD_ANCHOR,
          }))
          // Advanced markers fire 'gmp-click'.
          mk.addEventListener('gmp-click', () => selectPin(h))
          markers.current.set(h.id, mk)
        }
      }).catch(() => {})
    }

    const onIdle = () => { window.clearTimeout(timer); timer = window.setTimeout(fetchPins, 250) }
    const listener = map.addListener('idle', onIdle)
    const onRefresh = () => fetchPins()
    window.addEventListener('whereq:hazards-refresh', onRefresh)
    fetchPins()
    return () => {
      window.clearTimeout(timer); listener.remove()
      window.removeEventListener('whereq:hazards-refresh', onRefresh)
    }
  }, [map, enabled, onSelect, AdvancedMarkerElement])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => clearAll(), [])  // eslint-disable-line react-hooks/exhaustive-deps

  return null
}
