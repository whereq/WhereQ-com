import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MapSelection } from '@/types/selection'
import { placesApi } from '@/lib/placesApi'
import { localApi } from '@/lib/localApi'
import { useStories } from '@/hooks/useStories'
import { useSavedPlaces } from '@/hooks/useSavedPlaces'
import { useAuth } from '@/contexts/AuthContext'
import { useMapContext } from '@/contexts/MapContext'
import { hazardsApi } from '@/lib/hazardsApi'
import { geoApi } from '@/lib/geoApi'
import type { GeoAtPlace } from '@/types/geo'
import type { SchoolBoundaryRequest } from '@/contexts/MapContext'
import { formatFreshness, formatPriceItems } from '@/components/map/placeMarkers'
import { idealText } from '@/components/map/popupCard'
import { resolveColor } from '@/lib/searchColors'

/** The record behind a place id ("place-12" → 12). */
function numericId(id: string): number | undefined {
  const n = Number(id.replace(/^[a-z]+-/, ''))
  return Number.isFinite(n) ? n : undefined
}

/**
 * Load what the map pin does not carry: the address, the opening hours, the
 * price panel, the news summary, the story.
 */
function useEnriched(sel: MapSelection): MapSelection {
  // The extra detail is stamped with the id it was loaded for, so a card that
  // switches to another place never shows the previous one's address.
  const [loaded, setLoaded] = useState<{ id: string; extra: Partial<MapSelection> }>({ id: '', extra: {} })
  const storyPlaceId = sel.kind === 'memorial' ? sel.placeId : undefined
  const { stories } = useStories(storyPlaceId)

  useEffect(() => {
    let cancelled = false
    setLoaded({ id: sel.id, extra: {} })

    if (sel.kind === 'poi' && sel.placeId != null) {
      placesApi.detail(sel.placeId).then(d => {
        if (cancelled) return
        const meta = (d.metadata_json ?? {}) as Record<string, unknown>
        const items = formatPriceItems(meta.prices)
        setLoaded({ id: sel.id, extra: {
          address: d.address,
          city: d.city,
          description: d.description,
          phone: typeof meta.phone === 'string' ? meta.phone : null,
          website: typeof meta.website === 'string' ? meta.website : null,
          hours: typeof meta.opening_hours === 'string' ? meta.opening_hours : null,
          prices: items.length
            ? {
                items,
                unit: typeof meta.unit === 'string' ? meta.unit : null,
                note: formatFreshness(meta.observed_at) ?? null,
              }
            : null,
        } })
      }).catch(() => { /* the pin data is still worth showing */ })
    } else if (sel.kind === 'local') {
      const id = numericId(sel.id)
      if (id != null) {
        localApi.detail(id).then(d => {
          if (cancelled) return
          setLoaded({ id: sel.id, extra: {
            body: d.summary || d.description,
            address: d.address,
            city: d.city,
            image: d.image_url,
            source: d.source_name,
            sourceUrl: d.source_url,
            when: d.event_time || d.publish_time,
          } })
        }).catch(() => { /* the pin data is still worth showing */ })
      }
    }

    return () => { cancelled = true }
  }, [sel.id, sel.kind, sel.placeId])

  // A memorial's story lives in its own table.
  const story = stories[0]
  const extra = loaded.id === sel.id ? loaded.extra : {}
  return {
    ...sel,
    ...extra,
    body: extra.body ?? (sel.kind === 'memorial' ? (story?.content ?? sel.body) : sel.body),
  }
}

/**
 * The administrative areas that contain a point.
 *
 * The geography feed answers locally (PostGIS `ST_Covers`), so this is one
 * cheap request per card. The two vocabularies — OpenStreetMap and
 * geoBoundaries — both come back, and the *same* place under both is shown
 * once: the app must not present "Ontario" twice. The dedupe key carries the
 * source, so two genuinely different places that happen to share a kind and
 * a name are both kept.
 */
function useContainment(lat: number, lng: number): GeoAtPlace[] {
  const [areas, setAreas] = useState<GeoAtPlace[]>([])

  useEffect(() => {
    let cancelled = false
    geoApi.at(lat, lng).then((res) => {
      if (cancelled) return
      const seen = new Set<string>()
      const unique: GeoAtPlace[] = []
      for (const p of res.places ?? []) {
        const key = `${p.kind}|${p.name}|${p.source}`
        if (seen.has(key)) continue
        seen.add(key)
        unique.push(p)
      }
      setAreas(unique)
    }).catch(() => { /* the card is still worth showing without the areas */ })
    return () => { cancelled = true }
  }, [lat, lng])

  return areas
}

/**
 * The catchment of the picked school, as the map layer found it.
 *
 * A school is not a point: it serves an *area*, and that area is the answer
 * to "where is this school?". So picking a school puts its catchment on the
 * map — the same orange the standalone schools app draws it in.
 *
 * The map layer owns the shape (the card is closed precisely so the user can
 * *look* at it, so the shape has to outlive the card) and publishes it here,
 * so the card can offer the chip that fits the map to it again.
 *
 * The catchment polygons are the school board's licensed data, so they are
 * gated: an anonymous visitor is offered the sign-in rather than a silent
 * nothing.
 */
function catchmentOf(
  sel: MapSelection,
  schoolBoundary: SchoolBoundaryRequest | null,
): SchoolBoundaryRequest | null {
  if (sel.kind !== 'school') return null
  const schoolId = numericId(sel.id)
  if (schoolId == null) return null
  if (schoolBoundary?.schoolId !== schoolId) return null
  return schoolBoundary
}

interface Props {
  selection: MapSelection
  /** Close the modal the card lives in (used by the actions). */
  onClose?: () => void
}

/**
 * The card every marker on the map opens.
 *
 * One presentation for every kind of pin — a POI, a school, a hazard, a news
 * item, a friend, a memorial or a searched address — with the map's own
 * colours and the same actions the old map popups had.
 */
export function PlaceCard({ selection, onClose }: Props) {
  const { t } = useTranslation()
  const { isAuthenticated, login } = useAuth()
  const { setSearchPin, requestGeoFocus, requestSchoolBoundary, schoolBoundary } = useMapContext()
  const sel = useEnriched(selection)
  const areas = useContainment(sel.lat, sel.lng)
  const catchment = catchmentOf(sel, schoolBoundary)
  const { savePlace, isSaved } = useSavedPlaces()
  const [saved, setSaved] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  const savedAlready = sel.placeId != null && isSaved(sel.placeId)
  const shownSaved = saved || savedAlready

  const directions = () => {
    onClose?.()
    window.dispatchEvent(new CustomEvent('whereq:directions-to', {
      detail: { lat: sel.lat, lng: sel.lng, label: sel.name },
    }))
  }

  const save = async () => {
    if (!isAuthenticated) { login(); return }
    if (sel.placeId == null) return
    try {
      await savePlace(sel.placeId, sel.name)
      setSaved(true)
    } catch { /* the shared fetch wrapper already reported it */ }
  }

  const share = async () => {
    const url = `https://www.google.com/maps/search/?api=1&query=${sel.lat},${sel.lng}`
    const text = `${sel.name} — ${sel.lat.toFixed(5)}, ${sel.lng.toFixed(5)}`
    if (navigator.share) {
      try { await navigator.share({ title: sel.name, text, url }); return } catch { /* dismissed */ }
    }
    try { await navigator.clipboard?.writeText(`${text}\n${url}`) } catch { /* no clipboard */ }
  }

  const confirmHazard = async () => {
    const id = numericId(sel.id)
    if (id == null) return
    try {
      await hazardsApi.confirm(id)
      setConfirmed(true)
      window.dispatchEvent(new CustomEvent('whereq:hazards-refresh'))
    } catch { /* the shared fetch wrapper already reported it */ }
  }

  const rows: { icon: string; text: string }[] = []
  // An area picked on the map is its own container — do not list it twice.
  const contained = sel.geo ? areas.filter(a => a.uid !== sel.geo!.uid) : areas
  const where = [sel.address, sel.city].filter(Boolean).join(', ')
  if (where) rows.push({ icon: '📍', text: where })
  if (sel.hours) rows.push({ icon: '🕐', text: sel.hours })
  if (sel.phone) rows.push({ icon: '📞', text: sel.phone })
  if (sel.website) rows.push({ icon: '🌐', text: sel.website })
  if (sel.source) rows.push({ icon: '📰', text: sel.source })
  if (sel.when) rows.push({ icon: '🕒', text: sel.when })
  if (sel.schoolType || sel.boardType) {
    rows.push({ icon: '🎓', text: [sel.schoolType, sel.boardType].filter(Boolean).join(' · ') })
  }
  if (sel.score != null) rows.push({ icon: '★', text: `${sel.score.toFixed(1)}/10` })
  if (sel.geo) {
    rows.push({ icon: '🗺️', text: t(`geo.kind.${sel.geo.kind}`, sel.geo.kind) })
    if (sel.geo.areaKm2 != null) {
      rows.push({ icon: '📐', text: `${sel.geo.areaKm2.toFixed(1)} km²` })
    }
  }
  if (sel.confirmations != null) {
    rows.push({
      icon: '🕐',
      text: t('poi.confirmedCount', { count: sel.confirmations }),
    })
  }

  const actions: { label: string; onClick: () => void; primary?: boolean }[] = []
  if (sel.kind === 'hazard') {
    actions.push({
      label: confirmed ? t('poi.confirmed', '✔ Confirmed') : t('poi.confirmHazard', 'Still here ✔'),
      onClick: confirmHazard, primary: !confirmed,
    })
  }
  if (sel.kind === 'school') {
    actions.push({ label: t('poi.openSchools', 'Open in Schools'), onClick: () => { window.location.href = '/schools' } })
  }
  if (sel.kind === 'local' && sel.sourceUrl) {
    actions.push({ label: t('poi.readMore', 'Read more ↗'), onClick: () => window.open(sel.sourceUrl!, '_blank', 'noopener') })
  }
  actions.push({ label: t('poi.directions', 'Directions →'), onClick: directions, primary: actions.length === 0 })
  if (sel.placeId != null) {
    actions.push({ label: shownSaved ? t('poi.saved', 'Saved ✓') : t('poi.save', 'Save'), onClick: save })
  }
  if (sel.kind !== 'school' && sel.kind !== 'hazard') {
    actions.push({ label: t('poi.share', 'Share'), onClick: () => void share() })
  }
  if (sel.isSearchPin) {
    actions.push({
      label: t('poi.clearPin', 'Remove pin'),
      onClick: () => { setSearchPin(null); onClose?.() },
    })
  }

  return (
    <div className="place-card">
      <div className="place-card-hd" style={{ background: sel.color, color: idealText(resolveColor(sel.color)) }}>
        {sel.kicker}
        {onClose && (
          <button className="place-card-x" onClick={onClose} aria-label={t('search.close', 'Close')}>✕</button>
        )}
      </div>
      <div className="place-card-bd">
        <div className="place-card-title">{sel.name}</div>
        {sel.subtitle && <div className="place-card-sub">{sel.subtitle}</div>}

        {sel.prices && sel.prices.items.length > 0 && (
          <div className="place-card-prices">
            {sel.prices.items.map(i => (
              <div key={i.label} className="place-card-price-row">
                <span>{i.label}</span>
                <b>{i.value}</b>
              </div>
            ))}
            {(sel.prices.unit || sel.prices.note) && (
              <div className="place-card-price-foot">
                <span>{sel.prices.note}</span>
                <span>{sel.prices.unit}</span>
              </div>
            )}
          </div>
        )}

        {rows.length > 0 && (
          <div className="place-card-rows">
            {rows.map((r, i) => (
              <div key={i} className="place-card-row">
                <span className="place-card-ic">{r.icon}</span>
                <span>{r.text}</span>
              </div>
            ))}
          </div>
        )}

        {/* The administrative areas the place falls in — broadest first.
            Each one carries its licence: both vocabularies may only be
            redistributed with attribution. Each one is also a **button**: the
            question that follows "contained in" is always "show me that one",
            and the answer is the outline drawn on the map. */}
        {contained.length > 0 && (
          <div className="place-card-areas">
            <div className="place-card-areas-h">{t('geo.containedIn', 'Contained in')}</div>
            <div className="place-card-areas-list">
              {contained.map(a => (
                <button
                  key={a.uid}
                  type="button"
                  className="chip-xs place-card-area"
                  title={t('geo.showOnMap', 'Show this area on the map')}
                  onClick={() => requestGeoFocus({
                    uid: a.uid, name: a.name, kind: a.kind, source: a.source,
                  })}
                >
                  <b>{a.name}</b>
                  <i>{t(`geo.kind.${a.kind}`, a.kind)}</i>
                  {a.license && <em>{a.license}</em>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* The school's own catchment — the area it serves, not the area it
            is in. It is drawn on the map as soon as the school is picked; the
            chip is the way to fit the map to it again. */}
        {sel.kind === 'school' && (catchment || !isAuthenticated) && (
          <div className="place-card-areas">
            <div className="place-card-areas-h">{t('school.catchment', 'Catchment')}</div>
            <div className="place-card-areas-list">
              {catchment ? (
                <button
                  type="button"
                  className="chip-xs place-card-area place-card-catchment"
                  title={t('geo.showOnMap', 'Show this area on the map')}
                  onClick={() => requestSchoolBoundary(catchment)}
                >
                  <b>{t('school.showCatchment', 'Show catchment')}</b>
                  <i>{t('school.catchmentArea', 'area served')}</i>
                </button>
              ) : (
                <button
                  type="button"
                  className="chip-xs place-card-area"
                  onClick={() => login()}
                >
                  <b>{t('school.signinForCatchment', 'Sign in to see the catchment')}</b>
                </button>
              )}
            </div>
          </div>
        )}

        {/* The attribution the open licences require. */}
        {sel.geo?.license && (
          <div className="place-card-attr">
            <span>{t('geo.dataBy', 'Data')}: {sel.geo.source}</span>
            {sel.geo.sourceUrl && (
              <a href={sel.geo.sourceUrl} target="_blank" rel="noopener noreferrer">
                {t('geo.sourceLink', 'source')}
              </a>
            )}
            <span className="lic">{sel.geo.license}</span>
          </div>
        )}

        {sel.image && (
          <div className="place-card-img">
            <img src={sel.image} alt="" referrerPolicy="no-referrer" />
          </div>
        )}

        {(sel.body || sel.description) && (
          <p className="place-card-body">{sel.body || sel.description}</p>
        )}

        <div className="place-card-acts">
          {actions.map(a => (
            <button
              key={a.label}
              className={`place-card-act${a.primary ? ' primary' : ''}`}
              onClick={a.onClick}
              style={a.primary ? { background: sel.color, color: idealText(resolveColor(sel.color)), borderColor: sel.color } : undefined}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
