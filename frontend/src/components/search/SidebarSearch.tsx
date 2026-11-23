import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SearchBox } from '@whereq/react'
import { useSearch, type SearchResult } from '@/hooks/useSearch'
import { useMapContext } from '@/contexts/MapContext'
import { useAuth } from '@/contexts/AuthContext'
import { resultColor } from '@/lib/searchColors'
import type { MapSelection } from '@/types/selection'

const IcSearch = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
  </svg>
)

/** The record behind an id ("place-12" → 12). */
function numericId(id: string): number | undefined {
  const n = Number(id.replace(/^[a-z]+-/, ''))
  return Number.isFinite(n) ? n : undefined
}

/**
 * whereq.com's colours, expressed as the shared library's `--wq-search-*`
 * tokens.
 *
 * The box itself is `@whereq/react`'s `SearchBox` — the field, the dropdown,
 * the keyboard navigation and the ARIA wiring are the same component every
 * whereq app uses. What is left here is whereq.com's own look (the tokens),
 * its own result rows (the coloured dot, the name, the context) and what
 * happens with a picked result.
 */
const SEARCH_THEME = {
  fieldBg: 'var(--surface-2)',
  fieldBorder: 'var(--border-2)',
  fieldBorderFocus: 'var(--accent)',
  text: 'var(--text)',
  placeholder: 'var(--muted)',
  icon: 'var(--text-2)',
  iconHover: 'var(--text)',
  listBg: 'var(--surface)',
  listBorder: 'var(--border-2)',
  listText: 'var(--text)',
  listDescription: 'var(--muted)',
  listActiveBg: 'var(--surface-2)',
  listActiveText: 'var(--text)',
  radius: 'var(--r-sm)',
  shadow: '0 14px 32px rgba(0, 0, 0, .38)',
  fontSize: '12.5px',
}

/**
 * The sidebar's own search box.
 *
 * It was a design mock-up for a long time — an input with no value, no
 * handler and no results — so "search the map" simply did not work from the
 * sidebar. It now runs the same `useSearch` hook as the ⌘K modal (our own
 * schools + POIs plus Google Places for addresses) and pans the map to the
 * picked result, which also leaves a pin on it and opens its card.
 *
 * **The box shows what is selected.** Picking a result puts the *name* of the
 * picked place in the box — "VAUGHAN WILLARD P.S." — because that is what the
 * user is looking at now, and the box is the place they look at to know where
 * they are. The text they typed ("vaughan") is not lost: it is the query
 * behind the box, and the × brings it back so the search can be refined.
 *
 * Searching needs a session, so a signed-out visitor gets a locked box that
 * asks them to sign in rather than a search that quietly returns nothing.
 */
export function SidebarSearch() {
  const { t } = useTranslation()
  const { focusSelection } = useMapContext()
  const { isAuthenticated, login } = useAuth()
  /** What the user typed — the live query. */
  const [query, setQuery] = useState('')
  /** The picked place, once one is picked: the box shows its name. */
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null)
  // A picked place ends the search: no more autocomplete calls for a query
  // the user has already answered.
  const { results, loading, resolve } = useSearch(query, 280, isAuthenticated && !selected)

  /** Pan the map to the picked result, drop a pin on it and open its card. */
  const pick = async (r: SearchResult) => {
    const coords = await resolve(r)
    if (!coords) return
    const kind: MapSelection['kind'] =
      r.kind === 'address' ? 'address' : r.kind === 'school' ? 'school' : 'poi'
    focusSelection({
      id: r.id,
      kind,
      name: r.name,
      kicker: kind === 'address'
        ? t('search.kickerAddress', 'Address')
        : kind === 'school'
          ? t('search.kickerSchool', 'School')
          : t('search.kickerPlace', 'Place'),
      subtitle: r.meta,
      color: resultColor(r),
      lat: coords.lat,
      lng: coords.lng,
      address: coords.address ?? null,
      placeId: kind === 'poi' ? numericId(r.id) : undefined,
      category: r.category,
      isSearchPin: true,
    })
    // The box now shows **what is selected**, not what was typed: the picked
    // place's name is the answer, and the box is where the user reads it. The
    // query stays behind it — the × brings the typed text back, so the search
    // can be refined without starting over.
    setSelected({ id: r.id, name: r.name })
  }

  // ── Signed out: a locked box that asks them to sign in ──────────
  if (!isAuthenticated) {
    return (
      <div className="side-search">
        <button className="side-search-locked" onClick={() => login()}>
          <IcSearch />
          <span className="side-search-locked-txt">
            {t('sidebarSearch.locked', 'Sign in to search addresses & places')}
          </span>
          <span className="side-search-lock">🔒</span>
        </button>
      </div>
    )
  }

  return (
    <div className="side-search">
      <SearchBox
        value={selected ? selected.name : query}
        onChange={(value) => {
          setSelected(null)
          setQuery(value)
        }}
        onClear={() => {
          if (selected) {
            // The picked place gives way to the query it came from: the
            // typed text is what the search is, and a picked place sitting
            // in the box would hide it.
            setSelected(null)
          } else {
            setQuery('')
          }
        }}
        onFocus={(e) => {
          // A picked name is a *value*, not something to append to: focusing
          // the box selects it, so the first keystroke replaces it.
          if (selected) e.currentTarget.select()
        }}
        suggestions={results.map((r) => ({ key: r.id, label: r.name, description: r.meta }))}
        onSelect={(s) => {
          const r = results.find((x) => x.id === s.key)
          if (r) void pick(r)
        }}
        renderOption={(s) => {
          const r = results.find((x) => x.id === s.key)
          if (!r) return null
          return (
            <>
              <span className="side-suggest-dot" style={{ background: resultColor(r) }} />
              <span className="side-suggest-name">{r.name}</span>
              <span className="side-suggest-meta">{r.meta}</span>
            </>
          )
        }}
        loading={loading}
        loadingText={t('sidebarSearch.searching')}
        emptyText={t('sidebarSearch.empty')}
        placeholder={t('sidebarSearch.placeholder')}
        clearLabel={t('sidebarSearch.clear')}
        theme={SEARCH_THEME}
      />
    </div>
  )
}
