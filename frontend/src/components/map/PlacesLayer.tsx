import { useEffect, useRef } from 'react'
import { useMap, useMapsLibrary } from '@vis.gl/react-google-maps'
import { MarkerClusterer, SuperClusterAlgorithm, type Cluster } from '@googlemaps/markerclusterer'
import { placesApi } from '@/lib/placesApi'
import { clusterIconUrl, clusterSize } from './localMarkers'
import { POI_CLUSTER_COLOR, POI_PIN_SIZE, poiIconUrl, poiStyle } from './placeMarkers'
import { popupListCard, type ListItem } from './popupCard'
import { ANCHOR_CENTER, clusterContent, iconContent, withModernListener } from './advancedMarkers'
import type { PlacePin } from '@/types/place'
import type { MapSelection } from '@/types/selection'

const PIN_CAP = 2000

interface Props {
  /** Essentials kinds to show (pharmacy/clinic/library/plaza). */
  kinds: string[]
  /** Quick-category POIs to show (food/coffee/fuel/parking/stays). */
  categories: string[]
  /** Selected food cuisines (OSM ids); empty = all food. */
  cuisines: string[]
  /** A marker was picked — the map opens that place's card. */
  onSelect: (sel: MapSelection) => void
}

/**
 * Viewport-driven, clustered Local Essentials + Quick Categories layer.
 * Mirrors LocalContentLayer: fetches /places/map by bounding box on idle,
 * renders distinct per-kind/category markers, and groups them with a
 * supercluster MarkerClusterer.
 */
export function PlacesLayer({ kinds, categories, cuisines, onSelect }: Props) {
  const map = useMap()
  // The marker library is loaded on demand; the advanced markers need it.
  const AdvancedMarkerElement = useMapsLibrary('marker')?.AdvancedMarkerElement
  const markers = useRef<Map<number, google.maps.marker.AdvancedMarkerElement>>(new Map())
  const pinFor = useRef<Map<google.maps.marker.AdvancedMarkerElement, PlacePin>>(new Map())
  const clusterer = useRef<MarkerClusterer | null>(null)
  const info = useRef<google.maps.InfoWindow | null>(null)
  const reqId = useRef(0)

  const clearAll = () => {
    clusterer.current?.clearMarkers()
    for (const [, mk] of markers.current) mk.map = null
    markers.current.clear()
    pinFor.current.clear()
    info.current?.close()
  }

  // Tear down when nothing is enabled.
  useEffect(() => {
    if (!map || kinds.length + categories.length > 0) return
    clearAll()
  }, [map, kinds.length, categories.length])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map || !AdvancedMarkerElement) return
    if (kinds.length + categories.length === 0) return
    let timer: number

    const ensureInfo = () => {
      if (!info.current) info.current = new window.google.maps.InfoWindow(
        { maxWidth: 300, headerDisabled: true } as google.maps.InfoWindowOptions & { headerDisabled?: boolean })
      return info.current
    }

    /** A picked pin → the card the map opens for it. */
    const selectPin = (pin: PlacePin) => {
      const st = poiStyle(pin)
      onSelect({
        id: `place-${pin.id}`,
        kind: 'poi',
        name: pin.title,
        kicker: st.label,
        subtitle: pin.sub ?? undefined,
        color: st.color,
        lat: pin.lat,
        lng: pin.lng,
        placeId: pin.id,
        category: pin.kind === 'poi' ? pin.category : pin.kind,
      })
    }

    // Cluster pick-list: clicking a small/unsplittable cluster shows its members
    // so the user lands on a specific place instead of between markers.
    const openList = (pins: PlacePin[], position: google.maps.LatLng) => {
      const iw = ensureInfo()
      const items: ListItem[] = pins.map((p) => ({
        id: p.id, name: p.title, color: poiStyle(p).color,
        meta: [poiStyle(p).label, p.sub ?? ''].filter(Boolean).join(' · '),
      }))
      iw.setContent(popupListCard(POI_CLUSTER_COLOR, `${pins.length} places here`, items))
      iw.setPosition(position)
      iw.open({ map })
      window.google.maps.event.addListenerOnce(iw, 'domready', () => {
        document.querySelectorAll<HTMLElement>('[data-pin]').forEach((el) => {
          el.addEventListener('click', () => {
            const pin = pins.find((p) => p.id === Number(el.dataset.pin))
            if (pin) {
              info.current?.close()
              selectPin(pin)
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
        .filter((p): p is PlacePin => !!p)
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
            cluster.count, POI_CLUSTER_COLOR, clusterIconUrl(size, POI_CLUSTER_COLOR), size,
          ),
          title: `${cluster.count} places`,
          zIndex: 100 + cluster.count,
          gmpClickable: true,
          ...ANCHOR_CENTER,
        }))
      },
    }

    if (!clusterer.current) {
      clusterer.current = new MarkerClusterer({
        map,
        renderer,
        onClusterClick,
        algorithm: new SuperClusterAlgorithm({ radius: 60, maxZoom: 18 }),
      })
    }

    const fetchPins = () => {
      const b = map.getBounds()
      if (!b) return
      const ne = b.getNorthEast(), sw = b.getSouthWest()
      const bbox = `${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`
      const id = ++reqId.current
      placesApi.map({ bbox, kinds, categories, cuisines, limit: PIN_CAP }).then((pins) => {
        if (id !== reqId.current || !map) return
        const next = new Set(pins.map((p) => p.id))
        for (const p of pins) {
          if (markers.current.has(p.id)) continue
          const st = poiStyle(p)
          const mk = withModernListener(new AdvancedMarkerElement({
            position: { lat: p.lat, lng: p.lng },
            content: iconContent(poiIconUrl(st.color, st.glyph, st.icon), POI_PIN_SIZE),
            title: p.title,
            // Advanced markers are not clickable unless asked to be.
            gmpClickable: true,
            ...ANCHOR_CENTER,
          }))
          // Advanced markers fire 'gmp-click'.
          mk.addEventListener('gmp-click', () => selectPin(p))
          markers.current.set(p.id, mk)
          pinFor.current.set(mk, p)
        }
        // Keep only in-view markers, then hand the set to the clusterer.
        for (const [pid, mk] of markers.current) {
          if (!next.has(pid)) { mk.map = null; pinFor.current.delete(mk); markers.current.delete(pid) }
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
  }, [map, kinds.join(','), categories.join(','), cuisines.join(','), onSelect, AdvancedMarkerElement])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => {
    clusterer.current?.clearMarkers()
    clusterer.current?.setMap(null)
    clusterer.current = null
    info.current?.close()
  }, [])

  return null
}
