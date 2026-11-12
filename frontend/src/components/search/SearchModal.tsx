import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { useSearch, type ResolvedPlace, type SearchResult } from '@/hooks/useSearch'
import { useFuelSearch, type FuelSearchResult } from '@/hooks/useFuelSearch'
import { useMapContext } from '@/contexts/MapContext'
import { useRouteContext } from '@/contexts/RouteContext'
import { useAuth } from '@/contexts/AuthContext'
import { resultColor } from '@/lib/searchColors'
import { NEARBY_CATEGORIES } from '@/lib/nearbyCategories'
import type { NearbyItem } from '@/types/nearby'
import type { MapSelection } from '@/types/selection'
import { NearbyList } from './NearbyList'
import { PlaceCard } from './PlaceCard'

/** The record behind an id ("place-12" → 12). */
function numericId(id: string): number | undefined {
  const n = Number(id.replace(/^[a-z]+-/, ''))
  return Number.isFinite(n) ? n : undefined
}

export function SearchModal() {
  const { t } = useTranslation()
  const {
    searchOpen, searchMode, selection,
    closeSearch, openSearch, selectPlace, focusSelection,
    mapCenter, mapBbox,
  } = useMapContext()
  const route = useRouteContext()
  const location = useLocation()
  const navigate = useNavigate()
  // The gas prices are crawled from whereq.cloud (licensed, metered) — signed-in
  // users only, like the Google Places autocomplete.
  const { isAuthenticated, login } = useAuth()
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'distance' | 'price'>('distance')
  /**
   * The result the place on screen came from: its id, and whether it came
   * from the *text* search (as opposed to the nearby list or the gas list).
   * The field is only shown while that place is the one on screen — otherwise
   * the box would still read "Pan Am Centre" above the card of somewhere
   * else.
   */
  const [searched, setSearched] = useState<{ id: string; text: boolean } | null>(null)
  /**
   * The text search stays **enabled in the place view** of a text search: the
   * place was found by that text, so its results (and its billable
   * autocomplete session) must survive the trip to the card and back.
   * Re-enabling the search later would start a *second* session for the same
   * string. A place that came from the nearby list or the gas list has no
   * text search behind it, so nothing stays enabled for it.
   */
  const textSearch = searchMode === 'all' || searchMode === 'stop'
    || (searchMode === 'place' && searched?.text === true)
  const { results, loading, resolve } = useSearch(query, 280, textSearch)
  const fuel = useFuelSearch({
    query, enabled: searchMode === 'gas' && isAuthenticated,
    center: mapCenter, bbox: mapBbox, sort,
  })
  const inputRef = useRef<HTMLInputElement>(null)
  const [activeIdx, setActiveIdx] = useState(0)

  // The field takes the focus when the modal opens — not on the place card:
  // that is what the user just asked for. (Only on open: widening this to the
  // mode would pop the keyboard every time a filter chip is tapped.)
  useEffect(() => {
    if (searchOpen && searchMode !== 'place') inputRef.current?.focus()
  }, [searchOpen])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setActiveIdx(0) }, [results, fuel.results])

  // A fresh session starts with an empty box. The query is cleared when the
  // modal *closes*, so it is already empty when it opens again — clearing it
  // on open would paint the previous session's text for a frame first.
  useEffect(() => {
    if (searchOpen) return
    setQuery('')
    setSearched(null)
    setActiveIdx(0)
  }, [searchOpen])

  // Escape closes the modal from anywhere inside it — the filter chips and the
  // radius buttons are focusable, so listening on the input alone is not
  // enough (the same pattern the dropdown uses). The listener only exists
  // while the modal is open, so Escape is not swallowed by the rest of the app.
  useEffect(() => {
    if (!searchOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeSearch()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [closeSearch, searchOpen])

  // Typing a fuel word jumps straight to the gas stations — that's what
  // someone looking for "gas" wants, not a list of OSM places named "Gas".
  // The nearby tab is left alone: it is a deliberate choice, not a search.
  const lastQuery = useRef('')
  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (q === lastQuery.current) return
    lastQuery.current = q
    if (!isAuthenticated) return
    const isFuel = /\b(gas|petrol|gasoline|fuel)\b/.test(q)
    // A fuel word jumps to the gas stations — and editing it back out jumps
    // again, so the search never gets stranded in a tab with no results.
    if (isFuel && (searchMode === 'all' || searchMode === 'stop')) openSearch('gas')
    else if (!isFuel && searchMode === 'gas') openSearch('all')
  }, [query, isAuthenticated, searchMode, openSearch])

  /** A search result → the selection the card shows. */
  const selectionFromResult = (r: SearchResult | FuelSearchResult, coords: ResolvedPlace): MapSelection => {
    const sr = r as SearchResult
    const kind: MapSelection['kind'] =
      sr.kind === 'address' ? 'address' : sr.kind === 'school' ? 'school' : 'poi'
    const placeId = sr.id.startsWith('place-') ? numericId(sr.id) : undefined
    return {
      id: sr.id,
      kind,
      name: sr.name,
      kicker: kind === 'address'
        ? t('search.kickerAddress', 'Address')
        : kind === 'school'
          ? t('search.kickerSchool', 'School')
          : t('search.kickerPlace', 'Place'),
      subtitle: sr.meta,
      color: resultColor(sr),
      lat: coords.lat,
      lng: coords.lng,
      address: coords.address ?? null,
      placeId: kind === 'poi' ? placeId : undefined,
      category: sr.category,
      isSearchPin: true,
    }
  }

  /** A row of the nearby list → the selection the card shows. */
  const selectionFromNearby = (item: NearbyItem): MapSelection => {
    const cat = NEARBY_CATEGORIES.find(c => c.id === item.category)
    const kind: MapSelection['kind'] =
      item.type === 'school' ? 'school'
        : item.type === 'hazard' ? 'hazard'
          : item.type === 'local' ? 'local' : 'poi'
    return {
      id: item.id,
      kind,
      name: item.name,
      kicker: cat ? t(cat.labelKey) : kind === 'local' ? t('nearby.news') : t('search.kickerPlace', 'Place'),
      subtitle: item.meta ?? undefined,
      color: cat?.color ?? 'var(--accent)',
      lat: item.lat,
      lng: item.lng,
      category: item.category,
      placeId: item.type === 'place' ? numericId(item.id) : undefined,
    }
  }

  const choose = async (r: SearchResult | FuelSearchResult) => {
    // A route stop: the trip planner asked for one.
    if (searchMode === 'stop') {
      const coords = r.lat != null && r.lng != null
        ? { lat: r.lat, lng: r.lng }
        : await resolve(r as SearchResult)
      if (coords) route.addStop({ lat: coords.lat, lng: coords.lng, label: r.name })
      closeSearch()
      return
    }
    // Fuel results already carry coordinates; the others may need resolving.
    const coords = r.lat != null && r.lng != null
      ? { lat: r.lat, lng: r.lng }
      : await resolve(r as SearchResult)
    if (!coords) return
    // The map lives on the home route — go there first, so the pan and the
    // pin land on a map that is actually mounted.
    if (location.pathname !== '/') navigate('/')
    // Pan to it, leave a pin on it and open its card.
    setSearched({ id: r.id, text: searchMode !== 'gas' })
    focusSelection(selectionFromResult(r, coords))
  }

  const visible: (SearchResult | FuelSearchResult)[] = searchMode === 'gas' ? fuel.results : results
  const busy = searchMode === 'gas' ? fuel.loading : loading

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      closeSearch()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, Math.max(visible.length - 1, 0)))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && searchMode === 'place') {
      // The place view has no list of its own — Enter goes back to the
      // results for the text that is still in the box.
      e.preventDefault()
      openSearch('all')
    } else if (e.key === 'Enter' && visible[activeIdx]) {
      e.preventDefault()
      void choose(visible[activeIdx])
    }
  }

  /**
   * Editing the field always returns to the results list: a search in
   * progress is not a place card. (In the nearby tab the text filters that
   * list instead — it is not a search, so it stays put.)
   */
  const onQueryChange = (v: string) => {
    if (searchMode === 'place') {
      openSearch('all')
      // The view changes under the field — hand the focus back to it.
      requestAnimationFrame(() => inputRef.current?.focus())
    }
    setQuery(v)
  }

  /**
   * The search field. It is shown in two places: the search view, and — when
   * the place came from a search — above the picked place's card, so the text
   * the user searched for stays on screen with its answer.
   */
  const inputRow = (
    <div className="search-modal-input-wrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
      </svg>
      <input
        ref={inputRef}
        className="search-modal-input"
        placeholder={t('search.placeholder')}
        value={query}
        onChange={e => onQueryChange(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <kbd className="search-modal-esc">Esc</kbd>
    </div>
  )

  if (!searchOpen) return null

  // ── The sign-in wall ───────────────────────────────────────────
  // Searching needs a session: the addresses come from Google Places and the
  // gas prices from whereq.cloud. Guests are told so plainly instead of being
  // shown a search that quietly returns nothing.
  //
  // The wall covers the *searches* only. Opening a marker (the place card and
  // the nearby list around it) is browsing, and both are free — a guest who
  // clicks a pin still gets its card.
  const isSearch = searchMode === 'all' || searchMode === 'gas' || searchMode === 'stop'
  if (!isAuthenticated && isSearch) {
    return (
      <div className="search-modal-overlay" onClick={closeSearch}>
        <div className="search-modal search-modal-signin" onClick={e => e.stopPropagation()}>
          <div className="signin-wall">
            <div className="signin-wall-ic">🔒</div>
            <div className="signin-wall-title">{t('search.signinTitle', 'Sign in to search')}</div>
            <div className="signin-wall-text">
              {t('search.signinText',
                'Searching streets & addresses uses Google Places, and your radius and categories are kept on your account. Sign in to use them.')}
            </div>
            <button className="signin-wall-btn" onClick={() => login()}>
              {t('signin')}
            </button>
            <button className="signin-wall-later" onClick={closeSearch}>
              {t('search.signinLater', 'Not now')}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── The picked place ───────────────────────────────────────────
  // Every marker on the map opens this: the place itself, and what is around
  // it (the same nearby list, the same radius and category settings).
  if (searchMode === 'place' && selection) {
    return (
      <div className="search-modal-overlay" onClick={closeSearch}>
        <div className="search-modal search-modal-place" onClick={e => e.stopPropagation()}>
          {/* The searched text stays on screen with its answer — but only for
              the place that search produced. A place opened from a marker (or
              from the nearby list) has no search behind it, so it shows the
              card alone rather than a field that disagrees with it. */}
          {searched?.id === selection.id && inputRow}
          <PlaceCard key={selection.id} selection={selection} onClose={closeSearch} />
          <div className="place-nearby-hd">{t('search.nearbyAround', 'What is around it')}</div>
          <NearbyList
            center={{ lat: selection.lat, lng: selection.lng }}
            query=""
            onSelectItem={item => selectPlace(selectionFromNearby(item))}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="search-modal-overlay" onClick={closeSearch}>
      <div className="search-modal" onClick={e => e.stopPropagation()}>
        {inputRow}

        {/* Filter rail: the text search, the gas stations, or everything
            nearby within the saved radius. (In stop-picking mode the rail is
            hidden — the trip planner asked for one place, not a tab.) */}
        {searchMode !== 'stop' && (
          <div className="search-modal-filters">
            <button
              className={`search-modal-filter${searchMode === 'all' ? ' on' : ''}`}
              onClick={() => openSearch('all')}
            >
              {t('searchFilters.all', 'Everything')}
            </button>
            <button
              className={`search-modal-filter${searchMode === 'nearby' ? ' on' : ''}`}
              onClick={() => openSearch('nearby')}
            >
              {t('nearby.tab', 'Nearby')}
            </button>
            <button
              className={`search-modal-filter${searchMode === 'gas' ? ' on' : ''}`}
              onClick={() => { if (!isAuthenticated) { login(); return } openSearch('gas') }}
              title={isAuthenticated ? undefined : t('searchFilters.gasGated', 'Sign in to see gas prices')}
            >
              {t('searchFilters.gas', 'Gas stations')}
              {!isAuthenticated && <span className="search-modal-lock">🔒</span>}
            </button>
            {searchMode === 'gas' && isAuthenticated && (
              <button
                className="search-modal-sort"
                onClick={() => setSort(sort === 'distance' ? 'price' : 'distance')}
              >
                {sort === 'distance'
                  ? t('searchFilters.nearest', 'Nearest')
                  : t('searchFilters.cheapest', 'Cheapest')}
              </button>
            )}
          </div>
        )}

        {searchMode === 'nearby' ? (
          <NearbyList
            center={mapCenter}
            query={query}
            onSelectItem={item => selectPlace(selectionFromNearby(item))}
          />
        ) : (
          (query.trim() || searchMode === 'gas') && (
            <div className="search-modal-results">
              {busy && <div className="search-modal-status">Searching…</div>}
              {!busy && visible.length === 0 && (
                <div className="search-modal-status">No results found</div>
              )}
              {visible.map((r, idx) => (
                <button
                  key={r.id}
                  className={`search-modal-item${idx === activeIdx ? ' active' : ''}`}
                  onClick={() => void choose(r)}
                  onMouseEnter={() => setActiveIdx(idx)}
                >
                  <span className="search-modal-dot" style={{ background: resultColor(r as SearchResult) }} />
                  <span className="search-modal-name">{r.name}</span>
                  <span className="search-modal-meta">{r.meta}</span>
                </button>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  )
}
