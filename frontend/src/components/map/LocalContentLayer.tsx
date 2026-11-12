import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useMap, useMapsLibrary } from '@vis.gl/react-google-maps'
import { MarkerClusterer, SuperClusterAlgorithm, type Cluster } from '@googlemaps/markerclusterer'
import { localApi } from '@/lib/localApi'
import {
  CATEGORY_LABELS, categoryColor, clusterIconUrl, clusterSize, formatWhen,
  LOCAL_CLUSTER_COLOR, LOCAL_PIN_SIZE, localPinIconUrl,
} from './localMarkers'
import { popupListCard } from './popupCard'
import { ANCHOR_CENTER, clusterContent, iconContent, withModernListener } from './advancedMarkers'
import type { LocalPin } from '@/types/local'
import type { MapSelection } from '@/types/selection'

const PIN_CAP = 1500

interface Props {
  enabledTypes: string[]      // empty = layer off
  categories: string[]        // empty = all
  sources: string[]           // empty = all
  fromIso?: string            // publish_time lower bound
  onCount?: (n: number, capped: boolean) => void
  /** A marker was picked — the map opens that item's card. */
  onSelect?: (sel: MapSelection) => void
}

/**
 * Imperative local-content marker layer driven by the map viewport.
 *
 * Markers use a distinctive rounded-square "chip" icon (so they don't blend
 * with Google POI dots / the app's teardrop pins) and are grouped by a
 * supercluster-based MarkerClusterer: nearby pins merge into a count bubble
 * that splits apart as you zoom in. Items stacked at (essentially) the same
 * location can't be split by zoom, so clicking such a cluster opens a list
 * popup of all the items there.
 */
export function LocalContentLayer({ enabledTypes, categories, sources, fromIso, onCount, onSelect }: Props) {
  const map = useMap()
  const { t } = useTranslation()
  // The marker library is loaded on demand; the advanced markers need it.
  const AdvancedMarkerElement = useMapsLibrary('marker')?.AdvancedMarkerElement
  const markers = useRef<Map<number, google.maps.marker.AdvancedMarkerElement>>(new Map())
  const pinFor = useRef<Map<google.maps.marker.AdvancedMarkerElement, LocalPin>>(new Map())
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

  // Tear down when the layer is disabled entirely.
  useEffect(() => {
    if (!map || enabledTypes.length > 0) return
    clearAll()
    onCount?.(0, false)
  }, [map, enabledTypes.length])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!map || !AdvancedMarkerElement) return
    if (enabledTypes.length === 0) return
    let timer: number

    const ensureInfo = () => {
      if (!info.current) info.current = new window.google.maps.InfoWindow(
        { maxWidth: 320, headerDisabled: true } as google.maps.InfoWindowOptions & { headerDisabled?: boolean })
      return info.current
    }

    /** A picked pin → the card the map opens for it. */
    const selectPin = (pin: LocalPin) => {
      onSelect?.({
        id: `local-${pin.id}`,
        kind: 'local',
        name: pin.title,
        kicker: CATEGORY_LABELS[pin.category] ?? t('nearby.news'),
        subtitle: [pin.source_name, formatWhen(pin.event_time || pin.publish_time)]
          .filter(Boolean).join(' · ') || undefined,
        color: categoryColor(pin.category),
        lat: pin.lat,
        lng: pin.lng,
        category: pin.category,
        source: pin.source_name,
        when: formatWhen(pin.event_time || pin.publish_time),
        image: pin.image_url,
      })
    }

    // List popup for a small/stacked cluster; each row flies to its item.
    const openList = (pins: LocalPin[], position: google.maps.LatLng) => {
      const iw = ensureInfo()
      const items = pins.map((p) => ({
        id: p.id,
        name: p.title,
        color: categoryColor(p.category),
        meta: [CATEGORY_LABELS[p.category] ?? p.category, p.source_name, formatWhen(p.event_time || p.publish_time)]
          .filter(Boolean).join(' · '),
      }))
      iw.setContent(popupListCard(LOCAL_CLUSTER_COLOR, `${pins.length} here`, items))
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

    // Cluster click. For a small cluster (or one that can't be split by zoom —
    // members on nearly the same point, or already at max zoom) show the pick
    // list so the user can jump straight to a specific item, instead of
    // fitBounds landing them between markers. Larger clusters zoom in to split.
    const onClusterClick = (_e: google.maps.MapMouseEvent, cluster: Cluster, m: google.maps.Map) => {
      const b = cluster.bounds
      const tiny = !b || (
        Math.abs(b.getNorthEast().lat() - b.getSouthWest().lat()) < 6e-4 &&
        Math.abs(b.getNorthEast().lng() - b.getSouthWest().lng()) < 6e-4
      )
      const atMax = (m.getZoom() ?? 0) >= 18
      const pins = (cluster.markers ?? [])
        .map((mk) => pinFor.current.get(mk as google.maps.marker.AdvancedMarkerElement))
        .filter((p): p is LocalPin => !!p)
      if (pins.length && (tiny || atMax || pins.length <= 20) && cluster.position) {
        openList(pins, cluster.position)
        return
      }
      if (b) m.fitBounds(b, 80)
    }

    const renderer = {
      render: (cluster: Cluster) => {
        const count = cluster.count
        const size = clusterSize(count)
        return withModernListener(new AdvancedMarkerElement({
          position: cluster.position,
          content: clusterContent(
            count, LOCAL_CLUSTER_COLOR, clusterIconUrl(size, LOCAL_CLUSTER_COLOR), size,
          ),
          title: `${count} local items`,
          zIndex: 1000 + count,
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
        algorithm: new SuperClusterAlgorithm({ radius: 64, maxZoom: 18 }),
      })
    }

    const fetchPins = () => {
      const b = map.getBounds()
      if (!b) return
      const ne = b.getNorthEast(), sw = b.getSouthWest()
      const bbox = `${sw.lng()},${sw.lat()},${ne.lng()},${ne.lat()}`
      const id = ++reqId.current
      localApi.map({
        bbox, types: enabledTypes, categories, sources, from: fromIso, limit: PIN_CAP + 1,
      }).then((pins) => {
        if (id !== reqId.current || !map) return
        const capped = pins.length > PIN_CAP
        const shown = capped ? pins.slice(0, PIN_CAP) : pins
        onCount?.(pins.length, capped)

        const next = new Set(shown.map((p) => p.id))
        // Drop markers that left the viewport / filter.
        for (const [pid, mk] of markers.current) {
          if (!next.has(pid)) { mk.map = null; pinFor.current.delete(mk); markers.current.delete(pid) }
        }
        // Add markers that are newly in view.
        for (const p of shown) {
          if (markers.current.has(p.id)) continue
          const mk = withModernListener(new AdvancedMarkerElement({
            position: { lat: p.lat, lng: p.lng },
            content: iconContent(localPinIconUrl(categoryColor(p.category), p.type), LOCAL_PIN_SIZE),
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
        // Hand the current marker set to the clusterer (it owns map placement).
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
  }, [map, enabledTypes.join(','), categories.join(','), sources.join(','), fromIso, onSelect, AdvancedMarkerElement])  // eslint-disable-line react-hooks/exhaustive-deps

  // Final cleanup on unmount.
  useEffect(() => () => {
    clusterer.current?.clearMarkers()
    clusterer.current?.setMap(null)
    clusterer.current = null
    info.current?.close()
  }, [])

  return null
}
