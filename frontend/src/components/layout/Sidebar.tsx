import { useTranslation } from 'react-i18next'
import { FaMountain, FaRoad, FaSatellite, FaTrain } from 'react-icons/fa6'
import { useMapContext } from '@/contexts/MapContext'
import { usePlacesContext } from '@/contexts/PlacesContext'
import { useRouteContext } from '@/contexts/RouteContext'
import { useFriendsContext } from '@/contexts/FriendsContext'
import { useAuth } from '@/contexts/AuthContext'
import { useSavedPlaces } from '@/hooks/useSavedPlaces'
import { useMyRoutes } from '@/hooks/useMyRoutes'
import { Button } from '@/components/ui/Button'
import { SidebarSearch } from '@/components/search/SidebarSearch'
import { FOOD_CUISINES } from '@/lib/foodCuisines'
import type { MapStyle } from '@/types/map'

/** Inline "sign in to use this" prompt for auth-gated sections. */
function SignInNote({ label, onSignIn }: { label: string; onSignIn: () => void }) {
  return <button className="signin-note" onClick={onSignIn}>{label}</button>
}

function metersBetween(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6371000
  const dLat = (b.lat - a.lat) * Math.PI / 180
  const dLng = (b.lng - a.lng) * Math.PI / 180
  const la1 = a.lat * Math.PI / 180, la2 = b.lat * Math.PI / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

function fmtDist(m: number): string {
  return m < 1000 ? `${Math.round(m)}m` : `${(m / 1000).toFixed(1)}km`
}

// ── Small icon components ──────────────────────────────────────
const IcSearch = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
  </svg>
)
const IcLayers = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="m12 2 10 6-10 6L2 8z" /><path d="m2 14 10 6 10-6" /><path d="m2 11 10 6 10-6" opacity=".5" />
  </svg>
)
const IcArrowUR = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M7 17 17 7M9 7h8v8" />
  </svg>
)
const IcBookmark = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m19 21-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </svg>
)
const IcTarget = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2.5" fill="currentColor" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
  </svg>
)

// ── Toggle switch ──────────────────────────────────────────────
function Toggle({ on, onChange, color = 'var(--accent)' }: { on: boolean; onChange: (v: boolean) => void; color?: string }) {
  return (
    <span
      className={`tog ${on ? 'on' : ''}`}
      style={{ '--c': color } as React.CSSProperties}
      onClick={(e) => { e.stopPropagation(); onChange(!on) }}
    />
  )
}

// ── Map style ───────────────────────────────────────────────
/**
 * The map style: four choices, one row.
 *
 * This used to be a 2×2 grid of 56 px cards that drew each style by hand with
 * CSS gradients — the transit one was two crossing diagonals, which read as a
 * "close" X rather than as a transit map. The icons now come from
 * **react-icons**, the set the whereq universe uses everywhere else, and the
 * control is the **chip role**: a single choice, in a row.
 */
const MAP_STYLES = [
  { id: 'streets', icon: FaRoad, label: 'layers.streets' },
  { id: 'satellite', icon: FaSatellite, label: 'layers.satellite' },
  { id: 'terrain', icon: FaMountain, label: 'layers.terrain' },
  { id: 'transit', icon: FaTrain, label: 'layers.transit' },
] as const

function MapStylePicker({ value, onChange }: { value: MapStyle; onChange: (s: MapStyle) => void }) {
  const { t } = useTranslation()
  return (
    <div className="chip-rail style-rail">
      {MAP_STYLES.map(s => (
        <button
          key={s.id}
          type="button"
          className={`chip-xs style-chip${value === s.id ? ' on' : ''}`}
          onClick={() => onChange(s.id)}
          title={t(s.label)}
          aria-label={t(s.label)}
          aria-pressed={value === s.id}
        >
          <s.icon size={13} />
          <span>{t(s.label)}</span>
        </button>
      ))}
    </div>
  )
}

// ── Category dot ───────────────────────────────────────────────
function CategoryDot({ cat }: { cat: string }) {
  const colors: Record<string, string> = {
    coffee: '#A0763C', food: '#FF7A4D', parking: '#5BA5FF', fuel: '#4ADE80', stays: '#B388FF',
  }
  return <span style={{ width: 6, height: 6, borderRadius: '50%', background: colors[cat] || 'var(--accent)', display: 'inline-block' }} />
}

// ── Score bar ──────────────────────────────────────────────────
function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="score">
      <div className="score-l">
        <span className="score-lbl">{label}</span>
        <span className="score-val">{value}</span>
      </div>
      <div className="score-track">
        <div className="score-fill" style={{ width: value + '%', background: color }} />
      </div>
    </div>
  )
}

// ── Essential icon ─────────────────────────────────────────────
function EssIcon({ k }: { k: string }) {
  if (k === 'school') return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
      <polygon points="8,2 14,5 8,8 2,5" />
      <path fill="none" stroke="currentColor" strokeWidth="1.4" d="M3 6v3a5 3 0 0 0 10 0V6" />
    </svg>
  )
  if (k === 'rx') return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
      <rect x="7" y="3" width="2" height="10" /><rect x="3" y="7" width="10" height="2" />
    </svg>
  )
  if (k === 'plus') return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M8 3v10M3 8h10" />
    </svg>
  )
  if (k === 'plaza') return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
      <rect x="3" y="3" width="10" height="10" transform="rotate(45 8 8)" /><circle cx="8" cy="8" r="1.2" fill="currentColor" />
    </svg>
  )
  if (k === 'book') return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M3 3h4a2 2 0 0 1 2 2v8a2 2 0 0 0-2-2H3z" /><path d="M13 3H9a2 2 0 0 0-2 2v8a2 2 0 0 1 2-2h4z" />
    </svg>
  )
  return null
}

// ── Essential row ──────────────────────────────────────────────
function EssRow({
  lab, count, sub, color, on, onToggle, icon,
}: { lab: string; count: number; sub?: string; color: string; on: boolean; onToggle: () => void; icon: string }) {
  return (
    <button className={`ess-row ${on ? 'on' : ''}`} onClick={onToggle}>
      <span className="ess-ic" style={{ background: color + '22', color }}>
        <EssIcon k={icon} />
      </span>
      <span className="ess-text">
        <span className="ess-lab">{lab}</span>
        {sub && <span className="ess-sub">{sub}</span>}
      </span>
      <span className="ess-ct" style={{ color: on ? color : 'var(--muted)' }}>{count}</span>
    </button>
  )
}

// ── Collapsed sidebar ──────────────────────────────────────────
function CollapsedSidebar({ onExpand }: { onExpand: () => void }) {
  return (
    <aside className="side collapsed">
      <div className="rail-icons">
        <button className="icon-btn active" onClick={onExpand} title="Expand"><IcSearch /></button>
        <button className="icon-btn" title="Layers"><IcLayers /></button>
        <button className="icon-btn" title="Directions"><IcArrowUR /></button>
        <button className="icon-btn" title="Saved"><IcBookmark /></button>
      </div>
    </aside>
  )
}

// ── Main Sidebar ───────────────────────────────────────────────
export function Sidebar() {
  const { t } = useTranslation()
  const {
    mapStyle, setMapStyle,
    filters, setFilters,
    categories, setCategories,
    cuisines, setCuisines,
    essentials, setEssentials,
    selectedSchool, setSelectedSchool,
    showNeighborhood, setShowNeighborhood,
    sidebarCollapsed, setSidebarCollapsed,
  } = useMapContext()
  const { pins, counts, neighborhood } = usePlacesContext()
  const route = useRouteContext()
  const { friends, myLocation } = useFriendsContext()
  const { isAuthenticated, login } = useAuth()
  const { savedPlaces } = useSavedPlaces()
  const { routes: myRoutes } = useMyRoutes()

  if (sidebarCollapsed) {
    return <CollapsedSidebar onExpand={() => setSidebarCollapsed(false)} />
  }

  const quickCats = [
    { id: 'food', lab: t('quick.food') },
    { id: 'coffee', lab: t('quick.coffee') },
    { id: 'fuel', lab: t('quick.fuel') },
    { id: 'parking', lab: t('quick.parking') },
    { id: 'stays', lab: t('quick.stays') },
  ]

  const toggleCat = (id: string) => {
    setCategories(categories.includes(id)
      ? categories.filter(c => c !== id)
      : [...categories, id])
  }

  const toggleCuisine = (id: string) => {
    setCuisines(cuisines.includes(id)
      ? cuisines.filter(c => c !== id)
      : [...cuisines, id])
  }

  const friendRows = friends
    .map(f => ({ ...f, dist: myLocation ? metersBetween(myLocation, { lat: f.lat, lng: f.lng }) : null }))
    .sort((a, b) => (a.dist ?? Infinity) - (b.dist ?? Infinity))

  const toggleFilter = (key: keyof typeof filters) => {
    setFilters({ ...filters, [key]: !filters[key] })
  }

  const schoolPin = selectedSchool ? pins.find(p => p.id === selectedSchool) : null

  return (
    <aside className="side scroll">
      {/* Filter search bar */}
      <SidebarSearch />

      <div className="side-body scroll">

        {/* NEIGHBORHOOD */}
        <div className="sect">
          <div className="sect-h">
            <span>{t('sect.nbhd')}</span>
            <button className="more" onClick={() => setShowNeighborhood(!showNeighborhood)}>
              {showNeighborhood ? t('nbhd.clear') : t('nbhd.show')}
            </button>
          </div>
          <div className="nbhd-card">
            <div className="nbhd-hd">
              <div className="nbhd-nm">{neighborhood?.name || t('nbhd.name')}</div>
              <div className="nbhd-rg">{neighborhood ? ([neighborhood.city, neighborhood.country].filter(Boolean).join(' · ') || t('nbhd.region')) : t('nbhd.region')}</div>
            </div>
            <div className="nbhd-scores">
              <ScoreBar label={t('nbhd.walk')} value={neighborhood?.walk ?? 0} color="var(--accent)" />
              <ScoreBar label={t('nbhd.transit')} value={neighborhood?.transit ?? 0} color="var(--info)" />
              <ScoreBar label={t('nbhd.bike')} value={neighborhood?.bike ?? 0} color="var(--success)" />
              <ScoreBar label={t('nbhd.greenery')} value={neighborhood?.greenery ?? 0} color="var(--warn)" />
            </div>
            {schoolPin && (
              <div className="nbhd-school-chip">
                <span className="ic-school" />
                <span>{schoolPin.title}{schoolPin.grade ? ` · ${schoolPin.grade}` : ''} · {t('nbhd.catchment')}</span>
                <button onClick={() => setSelectedSchool(null)} aria-label="clear">×</button>
              </div>
            )}
          </div>
        </div>

        {/* LOCAL ESSENTIALS */}
        <div className="sect">
          <div className="sect-h"><span>{t('sect.essentials')}</span></div>
          <div className="ess-grid">
            <EssRow lab={t('ess.schools')} count={counts.school ?? 0} sub="E · M · H · U" color="#E6B450"
              on={essentials.schools} onToggle={() => setEssentials({ ...essentials, schools: !essentials.schools })} icon="school" />
            <EssRow lab={t('ess.pharmacies')} count={counts.pharmacy ?? 0} color="#34D399"
              on={essentials.pharmacies} onToggle={() => setEssentials({ ...essentials, pharmacies: !essentials.pharmacies })} icon="rx" />
            <EssRow lab={t('ess.clinics')} count={counts.clinic ?? 0} color="#F87171"
              on={essentials.clinics} onToggle={() => setEssentials({ ...essentials, clinics: !essentials.clinics })} icon="plus" />
            <EssRow lab={t('ess.plazas')} count={counts.plaza ?? 0} color="#FB923C"
              on={essentials.plazas} onToggle={() => setEssentials({ ...essentials, plazas: !essentials.plazas })} icon="plaza" />
            <EssRow lab={t('ess.libraries')} count={counts.library ?? 0} color="#818CF8"
              on={essentials.libraries} onToggle={() => setEssentials({ ...essentials, libraries: !essentials.libraries })} icon="book" />
          </div>
        </div>

        {/* QUICK CATEGORIES */}
        <div className="sect">
          <div className="sect-h">
            <span>{t('sect.quick')}</span>
            <button className="more">{t('quick.more')}</button>
          </div>
          <div className="chips">
            {quickCats.map(c => (
              <Button key={c.id} variant="chip" selected={categories.includes(c.id)}
                onClick={() => toggleCat(c.id)}>
                <CategoryDot cat={c.id} /> {c.lab}
              </Button>
            ))}
          </div>
          {/* Food sub-categories (cuisines) — only when Food is on. */}
          {categories.includes('food') && (
            <>
              <div className="sub-h">{t('quick.cuisines', 'Cuisines')}</div>
              <div className="chips">
                {FOOD_CUISINES.map(cz => (
                  <Button key={cz.id} variant="chip" size="sm" selected={cuisines.includes(cz.id)}
                    onClick={() => toggleCuisine(cz.id)}>
                    {cz.label}
                  </Button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* MAP STYLE */}
        <div className="sect">
          <div className="sect-h"><span>{t('sect.layers')}</span></div>
          <MapStylePicker value={mapStyle} onChange={setMapStyle} />
        </div>

        {/* ON THE MAP filters */}
        <div className="sect">
          <div className="sect-h"><span>{t('sect.filters')}</span></div>
          <div className="tog-list">
            {([
              { key: 'friends' as const, color: 'var(--social)', meta: String(counts.friend ?? 0) },
              { key: 'memorial' as const, color: 'var(--memorial)', meta: String(counts.memorial ?? 0) },
              { key: 'hazards' as const, color: 'var(--danger)', meta: counts.hazard ? `${counts.hazard} live` : '' },
              { key: 'guides' as const, color: 'var(--warn)', meta: '' },
              { key: 'areas' as const, color: 'var(--geo)', meta: '' },
              { key: 'routes' as const, color: 'var(--info)', meta: '' },
              { key: 'weather' as const, color: 'var(--success)', meta: '' },
            ] as const).map(({ key, color, meta }) => (
              <div key={key} className="tog-row" onClick={() => toggleFilter(key)}>
                <span className="swatch" style={{ background: color }} />
                <span className="lab">
                  {t(`filters.${key}`)}
                  {meta && <span className="meta" style={{ marginLeft: 8 }}>{meta}</span>}
                </span>
                <Toggle on={filters[key]} color={color} onChange={() => toggleFilter(key)} />
              </div>
            ))}
          </div>
        </div>

        {/* TRIP PLANNER — routing uses the Google Directions API (billable), so
            it's gated behind sign-in. */}
        <div className="sect">
          <div className="sect-h"><span>{t('sect.planner')}</span></div>
          {!isAuthenticated ? (
            <SignInNote label={t('planner.signin', 'Sign in to plan routes & get directions')} onSignIn={login} />
          ) : (
          <div className="trip">
            <div className="row">
              <span className="dot a" />
              <div>
                <div className="txt">{t('planner.from')}</div>
                <div className="sub">{neighborhood ? [neighborhood.name, neighborhood.city].filter(Boolean).join(', ') || t('planner.here', 'Current location') : t('planner.here', 'Current location')}</div>
              </div>
              <span style={{ color: 'var(--muted)' }}><IcTarget /></span>
            </div>
            {route.stops.map((s, i) => (
              <div className="row" key={i}>
                <span className="dot b" />
                <div>
                  <div className="txt">{i === route.stops.length - 1 ? t('planner.to') : `${t('planner.stop', 'Stop')} ${i + 1}`}</div>
                  <div className="sub">{s.label || `${s.lat.toFixed(4)}, ${s.lng.toFixed(4)}`}</div>
                </div>
                <button className="trip-x" onClick={() => route.removeStop(i)} aria-label="remove">×</button>
              </div>
            ))}
            {route.stops.length === 0 && (
              <div className="trip-hint">{t('planner.hint', 'Search a place or tap “Directions” on the map')}</div>
            )}
            <button className="add" onClick={() => window.dispatchEvent(new CustomEvent('whereq:open-search-stop'))}>
              {t('planner.via', '+ Add stop')}
            </button>
            {route.active && (
              <>
                <div className="route-modes" style={{ marginTop: 8 }}>
                  {([['DRIVING', '🚗'], ['WALKING', '🚶'], ['BICYCLING', '🚲'], ['TRANSIT', '🚌']] as const).map(([m, icon]) => (
                    <button key={m} className={`route-mode${route.travelMode === m ? ' on' : ''}`}
                      title={m.toLowerCase()} onClick={() => route.setTravelMode(m)}>{icon}</button>
                  ))}
                </div>
                <div className="trip-result">{route.result ? `${route.result.distance} · ${route.result.duration}` : '…'}</div>
                <div className="go-row">
                  <button className="go" onClick={route.clear}>{t('planner.clear', 'Clear route')}</button>
                </div>
              </>
            )}
          </div>
          )}
        </div>

        {/* FRIENDS NEARBY */}
        <div className="sect">
          <div className="sect-h"><span>{t('sect.friends')}</span><button className="more">all</button></div>
          <div className="friends">
            {friendRows.length === 0 && (
              <div className="friends-empty">{t('friends.empty', 'No friends sharing location right now')}</div>
            )}
            {friendRows.map(f => (
              <div key={f.user_id} className="friend">
                <span className="av">{(f.username?.[0] ?? '?').toUpperCase()}</span>
                <div>
                  <div className="name">{f.username}</div>
                  <div className="where">{t('friends.sharing', 'Sharing location')}</div>
                </div>
                <span className="dist">{f.dist != null ? fmtDist(f.dist) : '—'}</span>
              </div>
            ))}
          </div>
        </div>

        {/* SAVED PLACES */}
        <div className="sect">
          <div className="sect-h"><span>{t('sect.saved')}</span></div>
          {!isAuthenticated ? (
            <SignInNote label={t('saved.signin', 'Sign in to save places')} onSignIn={login} />
          ) : savedPlaces.length === 0 ? (
            <div className="friends-empty">{t('saved.empty', 'No saved places yet')}</div>
          ) : (
            <div className="saved-list">
              {savedPlaces.map(s => (
                <div key={s.id} className="saved-item">
                  <span className="pin" style={{ background: 'var(--accent)' }} />
                  <span className="nm">{s.label || `Place #${s.place_id}`}</span>
                  <span className="ct" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* MY ROUTES */}
        <div className="sect">
          <div className="sect-h"><span>{t('sect.log')}</span></div>
          {!isAuthenticated ? (
            <SignInNote label={t('routes.signin', 'Sign in to see your routes')} onSignIn={login} />
          ) : myRoutes.length === 0 ? (
            <div className="friends-empty">{t('routes.empty', 'No routes yet')}</div>
          ) : (
            <div className="log">
              {myRoutes.map(r => (
                <div key={r.id} className="log-item">
                  <span className="bar" style={{ '--c': 'var(--accent)' } as React.CSSProperties} />
                  <div>
                    <div className="nm">{r.name}</div>
                    <div className="sub">{[
                      r.total_distance_km != null ? `${r.total_distance_km.toFixed(1)} km` : null,
                      r.duration_minutes != null ? `${r.duration_minutes} min` : null,
                    ].filter(Boolean).join(' · ')}</div>
                  </div>
                  <div className="d">{new Date(r.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </aside>
  )
}
