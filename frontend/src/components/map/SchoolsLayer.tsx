import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useMap, useMapsLibrary } from '@vis.gl/react-google-maps'
import { MarkerClusterer, SuperClusterAlgorithm, type Cluster } from '@googlemaps/markerclusterer'
import { schoolsMapApi, type SchoolMapPin } from '@/lib/schoolsMapApi'
import { clusterIconUrl, clusterSize } from './localMarkers'
import { popupListCard, type ListItem } from './popupCard'
import { ANCHOR_CENTER, clusterContent, iconContent, withModernListener } from './advancedMarkers'
import type { MapSelection } from '@/types/selection'

const PIN_CAP = 3000
const SCHOOL_COLOR = '#E6B450'        // amber — schools
const SCHOOL_CLUSTER_COLOR = '#E6B450'

function levelLetter(type: string | null): string {
  const t = (type || '').toLowerCase()
  if (t.includes('element')) return 'E'
  if (t.includes('middle')) return 'M'
  if (t.includes('second') || t.includes('high')) return 'H'
  if (t.includes('colleg')) return 'C'
  if (t.includes('univ')) return 'U'
  return 'S'
}

function schoolIconUrl(letter: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">`
    + `<rect x="6" y="7" width="16" height="16" rx="4" fill="#06090D" opacity="0.45"/>`
    + `<rect x="6" y="6" width="16" height="16" rx="4" fill="${SCHOOL_COLOR}" stroke="#FFFFFF" stroke-width="2"/>`
    + `<text x="14" y="17.5" text-anchor="middle" font-size="11" font-weight="800" fill="#2A1F0A"`
    + ` font-family="system-ui,sans-serif">${letter}</text></svg>`
  return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg)
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/**
 * Viewport-driven, clustered Schools layer for the main map, fed by
 * GET /schools/map (schools live in their own tables, not `places`).
 */
export function SchoolsLayer({ enabled, onSelect }: { enabled: boolean; onSelect: (sel: MapSelection) => void }) {
  const map = useMap()
  const { t } = useTranslation()
  // The marker library is loaded on demand; the advanced markers need it.
  const AdvancedMarkerElement = useMapsLibrary('marker')?.AdvancedMarkerElement
  const markers = useRef<Map<number, google.maps.marker.AdvancedMarkerElement>>(new Map())
  const pinFor = useRef<Map<google.maps.marker.AdvancedMarkerElement, SchoolMapPin>>(new Map())
  const clusterer = useRef<MarkerClusterer | null>(null)
  const info = useRef<google.maps.InfoWindow | null>(null)
  const reqId = useRef(0)

  useEffect(() => {
    if (!map || enabled) return
    clusterer.current?.clearMarkers()
    for (const [, mk] of markers.current) mk.map = null
    markers.current.clear()
    pinFor.current.clear()
    info.current?.close()
  }, [map, enabled])

  useEffect(() => {
    if (!map || !enabled || !AdvancedMarkerElement) return
    let timer: number

    const ensureInfo = () => {
      if (!info.current) info.current = new window.google.maps.InfoWindow(
        { maxWidth: 300, headerDisabled: true } as google.maps.InfoWindowOptions & { headerDisabled?: boolean })
      return info.current
    }

    /** A picked pin → the card the map opens for it. */
    const selectPin = (p: SchoolMapPin) => {
      const subtitle = [p.type, p.board_type].filter(Boolean).map((s) => cap(s as string)).join(' · ')
      onSelect({
        id: `school-${p.id}`,
        kind: 'school',
        name: p.name,
        kicker: t('search.kickerSchool', 'School'),
        subtitle: subtitle || undefined,
        color: SCHOOL_COLOR,
        lat: p.lat,
        lng: p.lng,
        schoolType: p.type,
        boardType: p.board_type,
        score: p.hs_score,
      })
    }

    const openList = (pins: SchoolMapPin[], position: google.maps.LatLng) => {
      const iw = ensureInfo()
      const items: ListItem[] = pins.map((p) => ({
        id: p.id, name: p.name, color: SCHOOL_COLOR,
        meta: [p.type, p.board_type].filter(Boolean).join(' · '),
      }))
      iw.setContent(popupListCard(SCHOOL_CLUSTER_COLOR, `${pins.length} schools here`, items))
      iw.setPosition(position)
      iw.open({ map })
      window.google.maps.event.addListenerOnce(iw, 'domready', () => {
        document.querySelectorAll<HTMLElement>('[data-pin]').forEach((el) => {
          el.addEventListener('click', () => {
            const p = pins.find((s) => s.id === Number(el.dataset.pin))
            if (p) {
              info.current?.close()
              selectPin(p)
            }
          })
        })
      })
    }

    const onClusterClick = (_e: google.maps.MapMouseEvent, cluster: Cluster, m: google.maps.Map) => {
      const b = cluster.bounds
      const tiny = !b || (
        Math.abs(b.getNorthEast().lat() - b.getSouthWest().lat()) < 6e-4 &&
        Math.abs(b.getNorthEast().lng() - b.getSouthWest().lng()) < 6e-4)
      const atMax = (m.getZoom() ?? 0) >= 18
      const pins = (cluster.markers ?? [])
        .map((mk) => pinFor.current.get(mk as google.maps.marker.AdvancedMarkerElement))
        .filter((p): p is SchoolMapPin => !!p)
      if (pins.length && (tiny || atMax || pins.length <= 20) && cluster.position) {
        openList(pins, cluster.position)
        return
      }
      if (b) m.fitBounds(b, 80)
    }

    const renderer = {
      render: (cluster: Cluster) => {
        const size = clusterSize(cluster.count)
        return withModernListener(new AdvancedMarkerElement({
          position: cluster.position,
          content: clusterContent(
            cluster.count, SCHOOL_CLUSTER_COLOR, clusterIconUrl(size, SCHOOL_CLUSTER_COLOR), size,
          ),
          title: `${cluster.count} schools`,
          zIndex: 50 + cluster.count,
          gmpClickable: true,
          ...ANCHOR_CENTER,
        }))
      },
    }

    if (!clusterer.current) {
      clusterer.current = new MarkerClusterer({
        map, renderer, onClusterClick,
        algorithm: new SuperClusterAlgorithm({ radius: 60, maxZoom: 18 }),
      })
    }

    const fetchPins = () => {
      const b = map.getBounds()
      if (!b) return
      const ne = b.getNorthEast(), sw = b.getSouthWest()
      const bbox = `${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`
      const id = ++reqId.current
      schoolsMapApi.map(bbox, PIN_CAP).then((pins) => {
        if (id !== reqId.current || !map) return
        const next = new Set(pins.map((p) => p.id))
        for (const [pid, mk] of markers.current) {
          if (!next.has(pid)) { mk.map = null; pinFor.current.delete(mk); markers.current.delete(pid) }
        }
        for (const p of pins) {
          if (markers.current.has(p.id)) continue
          const mk = withModernListener(new AdvancedMarkerElement({
            position: { lat: p.lat, lng: p.lng },
            content: iconContent(schoolIconUrl(levelLetter(p.type)), 28),
            title: p.name,
            // Advanced markers are not clickable unless asked to be.
            gmpClickable: true,
            ...ANCHOR_CENTER,
          }))
          // Advanced markers fire 'gmp-click'.
          mk.addEventListener('gmp-click', () => selectPin(p))
          markers.current.set(p.id, mk)
          pinFor.current.set(mk, p)
        }
        clusterer.current?.clearMarkers(true)
        clusterer.current?.addMarkers([...markers.current.values()])
      }).catch(() => {})
    }

    const onIdle = () => { window.clearTimeout(timer); timer = window.setTimeout(fetchPins, 250) }
    const listener = map.addListener('idle', onIdle)
    const onPopupClose = () => info.current?.close()
    window.addEventListener('whereq:popup-close', onPopupClose)
    fetchPins()
    return () => {
      window.clearTimeout(timer); listener.remove()
      window.removeEventListener('whereq:popup-close', onPopupClose)
    }
  }, [map, enabled, onSelect, AdvancedMarkerElement])

  useEffect(() => () => {
    clusterer.current?.clearMarkers()
    clusterer.current?.setMap(null)
    clusterer.current = null
    info.current?.close()
  }, [])

  return null
}
