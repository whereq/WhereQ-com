import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useMapContext } from '@/contexts/MapContext'
import { usePlacesContext } from '@/contexts/PlacesContext'
import { useAuth } from '@/contexts/AuthContext'
import { GoogleMapView } from './GoogleMapView'
import { LocalContentControls, type RangeKey } from './LocalContentControls'
import { useGeolocation } from '@/hooks/useGeolocation'
import { useDirections } from '@/hooks/useDirections'
import { useFriendsContext } from '@/contexts/FriendsContext'
import { useRouteContext } from '@/contexts/RouteContext'
import { hazardsApi, HAZARD_TYPES } from '@/lib/hazardsApi'
import { reportError } from '@/lib/errorBus'
import type { MapPin } from '@/types/map'
import type { MapSelection } from '@/types/selection'

const IcArrowR = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
)

export function MapArea() {
  const { t } = useTranslation()
  const { filters, categories, essentials, setSelectedSchool, mapCenter, focusRequest, clearFocus, selectPlace, dismissedSelection, reopenSearch } = useMapContext()
  const { pins, loading, neighborhood } = usePlacesContext()
  const { isAuthenticated, user, login } = useAuth()
  const geo = useGeolocation()
  const directions = useDirections()
  const friendsNet = useFriendsContext()
  const route = useRouteContext()

  const [focusTarget, setFocusTarget] = useState<{ lat: number; lng: number } | null>(null)
  const [showReport, setShowReport] = useState(false)
  const [reportType, setReportType] = useState('hazard')
  const [reportTitle, setReportTitle] = useState('')
  const [reportBusy, setReportBusy] = useState(false)

  // Local content (news/events/stories/topics) layer state
  const [localTypes, setLocalTypes] = useState<string[]>([])
  const [localCategories, setLocalCategories] = useState<string[]>([])
  const [localSources, setLocalSources] = useState<string[]>([])
  const [localRange, setLocalRange] = useState<RangeKey>('7d')
  const [localCount, setLocalCount] = useState(0)
  const [localCapped, setLocalCapped] = useState(false)

  const localFromIso = useMemo(() => {
    if (localRange === 'all') return undefined
    const days = { '24h': 1, '7d': 7, '30d': 30 }[localRange]
    return new Date(Date.now() - days * 86_400_000).toISOString()
  }, [localRange])

  const handleLocalCount = useCallback((n: number, capped: boolean) => {
    setLocalCount(n); setLocalCapped(capped)
  }, [])

  // Search-initiated place focus. The request comes from the map context, not
  // a window event, so a search made on another route still pans the map once
  // this page mounts.
  useEffect(() => {
    if (!focusRequest) return
    setFocusTarget({ lat: focusRequest.lat, lng: focusRequest.lng })
    clearFocus()
  }, [focusRequest, clearFocus])

  // Clear focus target after map consumes it
  const handleFocusConsumed = useCallback(() => setFocusTarget(null), [])

  // Start geolocation on mount
  useEffect(() => { geo.startWatching() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Live friend presence: connect the location WebSocket when signed in.
  useEffect(() => {
    if (!isAuthenticated) return
    friendsNet.connect()
    return () => friendsNet.disconnect()
  }, [isAuthenticated])  // eslint-disable-line react-hooks/exhaustive-deps

  // Broadcast our own position to friends as it updates; also publish it to the
  // friends context so the sidebar can compute distances.
  useEffect(() => {
    if (!geo.position) return
    friendsNet.setMyLocation({ lat: geo.position.lat, lng: geo.position.lng })
    if (isAuthenticated && friendsNet.connected) {
      friendsNet.sendLocation(geo.position.lat, geo.position.lng, user?.displayName ?? user?.username ?? 'me')
    }
  }, [isAuthenticated, friendsNet.connected, geo.position?.lat, geo.position?.lng])  // eslint-disable-line react-hooks/exhaustive-deps

  // Build "me" pin from real geolocation
  const geoPin: MapPin | null = geo.position ? {
    id: 'me-geo',
    x: 0, y: 0,
    lat: geo.position.lat,
    lng: geo.position.lng,
    kind: 'me',
    title: t('legend.me'),
  } : null

  // Real friend pins from live presence (replaces any mock 'friend' pins).
  const friendPins: MapPin[] = friendsNet.friends.map((f) => ({
    id: `friend-${f.user_id}`, x: 0, y: 0, lat: f.lat, lng: f.lng,
    kind: 'friend', title: f.username, initial: (f.username?.[0] ?? '?').toUpperCase(),
  }))

  // Merge geo + live friends with API pins (drop mock me/friend).
  const allPins = [
    ...(geoPin ? [geoPin] : []),
    ...friendPins,
    ...pins.filter(p => p.kind !== 'me' && p.kind !== 'friend'),
  ]

  // Every marker opens the same card — the search modal, scoped to that place.
  const handleSelectPlace = useCallback((sel: MapSelection) => selectPlace(sel), [selectPlace])

  /** A pin of the global set (me / friends / memorials). */
  const handleSelectPin = useCallback((pin: MapPin) => {
    if (pin.kind === 'memorial') {
      const placeId = Number(pin.id.replace('place-', ''))
      selectPlace({
        id: pin.id,
        kind: 'memorial',
        name: pin.title ?? '',
        kicker: t('legend.memorial'),
        subtitle: pin.sub ?? undefined,
        color: 'var(--memorial)',
        lat: pin.lat,
        lng: pin.lng,
        placeId: Number.isFinite(placeId) ? placeId : undefined,
        body: pin.story,
      })
      return
    }
    if (pin.kind === 'friend') {
      selectPlace({
        id: pin.id,
        kind: 'friend',
        name: pin.title ?? t('legend.friends'),
        kicker: t('legend.friends'),
        color: 'var(--social)',
        lat: pin.lat,
        lng: pin.lng,
        subtitle: t('friends.sharing', 'Sharing location'),
      })
      return
    }
    if (pin.kind === 'saved') {
      selectPlace({
        id: pin.id,
        kind: 'poi',
        name: pin.title ?? t('poi.save', 'Save'),
        kicker: t('poi.save', 'Save'),
        color: 'var(--accent)',
        lat: pin.lat,
        lng: pin.lng,
      })
      return
    }
    selectPlace({
      id: pin.id,
      kind: 'me',
      name: t('legend.me'),
      kicker: t('legend.me'),
      color: 'var(--accent)',
      lat: pin.lat,
      lng: pin.lng,
    })
  }, [selectPlace, t])

  const handleSelectSchool = (p: MapPin) => setSelectedSchool(p.id)

  // Popups/cards request directions (replace route) or add a stop, via events.
  // Routing uses the billable Google Directions API → signed-in users only.
  useEffect(() => {
    const toHandler = (e: Event) => {
      if (!isAuthenticated) { login(); return }
      route.routeTo((e as CustomEvent<{ lat: number; lng: number; label?: string }>).detail)
    }
    const addHandler = (e: Event) => {
      if (!isAuthenticated) { login(); return }
      route.addStop((e as CustomEvent<{ lat: number; lng: number; label?: string }>).detail)
    }
    // A place popup asking for the (licensed) fuel prices.
    const signInHandler = () => { if (!isAuthenticated) login() }
    window.addEventListener('whereq:directions-to', toHandler)
    window.addEventListener('whereq:add-stop', addHandler)
    window.addEventListener('whereq:signin', signInHandler)
    return () => {
      window.removeEventListener('whereq:directions-to', toHandler)
      window.removeEventListener('whereq:add-stop', addHandler)
      window.removeEventListener('whereq:signin', signInHandler)
    }
  }, [route, isAuthenticated, login])

  // Route executor: (re)compute whenever the stops, mode, or our location change.
  useEffect(() => {
    if (!isAuthenticated || route.stops.length === 0) { directions.clearDirections(); return }
    const origin = geo.position
      ? { lat: geo.position.lat, lng: geo.position.lng }
      : { lat: 43.6532, lng: -79.3832 } // fallback Toronto center
    const dest = route.stops[route.stops.length - 1]
    const waypoints = route.stops.slice(0, -1).map((s) => ({ lat: s.lat, lng: s.lng }))
    const gmode = (window as { google?: typeof google }).google?.maps?.TravelMode?.[route.travelMode]
    directions.getDirections(origin, { lat: dest.lat, lng: dest.lng }, gmode, waypoints)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.stops, route.travelMode, geo.position?.lat, geo.position?.lng, isAuthenticated])

  // Mirror the computed result back into the shared route state.
  useEffect(() => {
    route.setResult(directions.result
      ? { distance: directions.result.distance, duration: directions.result.duration }
      : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [directions.result])

  // Hazard reporting: drop a report at the current map center (auth required).
  const openReport = () => { if (!isAuthenticated) { login(); return } setShowReport(true) }
  const submitReport = async () => {
    if (!mapCenter || !reportTitle.trim()) return
    setReportBusy(true)
    try {
      await hazardsApi.create({
        type: reportType, severity: 'med', title: reportTitle.trim(),
        latitude: mapCenter.lat, longitude: mapCenter.lng,
      })
      window.dispatchEvent(new CustomEvent('whereq:hazards-refresh'))
      setShowReport(false); setReportTitle('')
      reportError('submitted', { code: 'toast.reportSubmitted', level: 'info' })
    } catch { /* the shared fetch wrapper already reported the failure */ } finally { setReportBusy(false) }
  }

  // Breadcrumb from neighborhood data
  const crumbCity = neighborhood?.city || t('crumb.city')
  const crumbArea = neighborhood
    ? ([neighborhood.name, neighborhood.country].filter(Boolean).join(' · ') || t('crumb.area'))
    : t('crumb.area')

  // The destination stop — the last one added. (Array.at() would need ES2022
  // runtime support; this matches the indexing used by the route executor.)
  const lastStop = route.stops[route.stops.length - 1]

  return (
    <div className="map-wrap">
      {loading && pins.length === 0 && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          zIndex: 10, color: 'var(--muted)', fontSize: 13,
        }}>
          Loading map data…
        </div>
      )}

      <GoogleMapView
        pins={allPins}
        showFriends={filters.friends}
        showMemorial={filters.memorial}
        showHazards={filters.hazards}
        showAreas={filters.areas}
        showCategories={categories}
        neighborhoodEssentials={essentials}
        onSelectMemorial={handleSelectPin}
        onSelectSchool={handleSelectSchool}
        onSelectPin={handleSelectPin}
        onSelectPlace={handleSelectPlace}
        focusTarget={focusTarget}
        onFocusConsumed={handleFocusConsumed}
        userLocation={geo.position ? { lat: geo.position.lat, lng: geo.position.lng } : null}
        localTypes={localTypes}
        localCategories={localCategories}
        localSources={localSources}
        localFromIso={localFromIso}
        onLocalCount={handleLocalCount}
      />

      {/* TR: local-content layer controls */}
      <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 6 }}>
        <LocalContentControls
          types={localTypes} setTypes={setLocalTypes}
          categories={localCategories} setCategories={setLocalCategories}
          sources={localSources} setSources={setLocalSources}
          range={localRange} setRange={setLocalRange}
          count={localCount} capped={localCapped}
        />
      </div>

      {/* TL: breadcrumb */}
      <div className="ovl ovl-tl">
        <div className="crumb">
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block' }} />
          <span className="city">{crumbCity}</span>
          <span className="sep">/</span>
          <span className="area">{crumbArea}</span>
        </div>
      </div>

      {/* BC: live route bar — only when there's an active route (no mock) */}
      {route.active && (
        <div className="ovl ovl-bc route-bar">
          <div className="arrow"><IcArrowR /></div>
          <div className="nav-text">
            <div className="dist">{route.result?.distance ?? '…'}{lastStop?.label ? ` · ${lastStop.label}` : ''}</div>
            <div className="step">{directions.loading ? '…' : (route.result?.duration ?? '')}</div>
          </div>
          <div className="route-modes">
            {([
              ['DRIVING', '🚗'], ['WALKING', '🚶'], ['BICYCLING', '🚲'], ['TRANSIT', '🚌'],
            ] as const).map(([m, icon]) => (
              <button key={m}
                className={`route-mode${route.travelMode === m ? ' on' : ''}`}
                title={m.toLowerCase()}
                onClick={() => route.setTravelMode(m)}>
                {icon}
              </button>
            ))}
          </div>
          <div className="eta">
            <div className="lbl">{t('route.eta')}</div>
            <b>{route.result?.duration ?? '…'}</b>
          </div>
          <button className="stop" onClick={route.clear}>{t('route.stop')}</button>
        </div>
      )}

      {/* Center crosshair while placing a hazard report */}
      {showReport && (
        <div style={{
          position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          width: 26, height: 26, borderRadius: '50%', border: '2px solid var(--danger)',
          boxShadow: '0 0 0 2px rgba(0,0,0,.35)', pointerEvents: 'none', zIndex: 7,
        }}>
          <div style={{ position: 'absolute', inset: '50% auto auto 50%', width: 4, height: 4, background: 'var(--danger)', borderRadius: '50%', transform: 'translate(-50%,-50%)' }} />
        </div>
      )}

      {/* BL: legend + report */}
      <div className="ovl ovl-bl" style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-start' }}>
        {/* The way back to a dismissed card. The card covers the middle of the
            map, so the user closes it to look at what is underneath — the
            boundary of an area, for one — and this brings it back while the
            user is still on the same place. */}
        {dismissedSelection && (
          <button
            className="reopen-card-btn"
            onClick={reopenSearch}
            title={t('search.reopenCard', 'Show the card again')}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12a9 9 0 1 0 3-6.7" />
              <path d="M3 4v5h5" />
            </svg>
            <span className="reopen-card-name">{dismissedSelection.name}</span>
          </button>
        )}
        {showReport ? (
          <div className="report-panel">
            <div className="report-hd">{t('report.title', 'Report at map center')}</div>
            <select value={reportType} onChange={(e) => setReportType(e.target.value)}>
              {HAZARD_TYPES.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
            </select>
            <input value={reportTitle} onChange={(e) => setReportTitle(e.target.value)}
              placeholder={t('report.what', "What's happening?")} maxLength={200} />
            <div className="report-acts">
              <button className="report-submit" disabled={!reportTitle.trim() || reportBusy} onClick={submitReport}>
                {reportBusy ? '…' : t('report.submit', 'Submit')}
              </button>
              <button className="report-cancel" onClick={() => setShowReport(false)}>{t('report.cancel', 'Cancel')}</button>
            </div>
          </div>
        ) : (
          <button className="report-btn" onClick={openReport} title={t('report.cta', 'Report a hazard')}>
            <svg width="14" height="13" viewBox="0 0 24 22" fill="none"><path d="M12 2 L22 20 L2 20 Z" fill="var(--danger)" stroke="white" strokeWidth="1.5" strokeLinejoin="round" /><text x="12" y="17" textAnchor="middle" fontSize="11" fontWeight="700" fill="white">!</text></svg>
            {t('report.cta', 'Report')}
          </button>
        )}
        <div className="legend">
          <span className="it"><span className="d" style={{ '--c': 'var(--accent)' } as React.CSSProperties} />{t('legend.me')}</span>
          <span className="it"><span className="d" style={{ '--c': 'var(--social)' } as React.CSSProperties} />{t('legend.friends')}</span>
          <span className="it"><span className="d" style={{ '--c': 'var(--memorial)' } as React.CSSProperties} />{t('legend.memorial')}</span>
          <span className="it"><span className="d" style={{ '--c': 'var(--danger)' } as React.CSSProperties} />{t('legend.hazard')}</span>
        </div>
      </div>
    </div>
  )
}
