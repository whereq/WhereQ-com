import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTheme } from '@/contexts/ThemeContext'
import { useAuth } from '@/contexts/AuthContext'
import { schoolsApi } from './api'
import { SC_I18N, scLocale, type ScLocale } from './i18n'
import { EMPTY_FILTERS, type CatchmentHit, type PaginatedSchools, type SchoolDetail as SchoolDetailT, type SchoolFilters, type SchoolSummary, type Taxonomy } from './types'
import { Filters } from './components/Filters'
import { SearchBox } from './components/SearchBox'
import { SchoolTable, type SortState } from './components/SchoolTable'
import { InfoPanel } from './components/InfoPanel'
import { SchoolDetail } from './components/SchoolDetail'
import { SchoolMap } from './components/SchoolMap'
import './schools.css'

const TORONTO = { lat: 43.6532, lng: -79.3832 }

function ScLogo() {
  return (
    <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
      <rect x="2" y="2" width="28" height="28" rx="3" fill="var(--accent)" />
      <text x="16" y="23" textAnchor="middle" fontSize="20" fontWeight="700" fontFamily="var(--font-display)" fill="var(--accent-ink)">Q</text>
    </svg>
  )
}

function Header({ t, locale, setLocale, theme, toggleTheme, mode, setMode, isAuthenticated, avatar, accountTitle, onAccount }: {
  t: typeof SC_I18N[ScLocale]; locale: ScLocale; setLocale: (l: ScLocale) => void
  theme: string; toggleTheme: () => void; mode: 'map' | 'list'; setMode: (m: 'map' | 'list') => void
  isAuthenticated: boolean; avatar: string | undefined; accountTitle: string; onAccount: () => void
}) {
  const [lopen, setLopen] = useState(false)
  const names: Record<ScLocale, string> = { en: 'EN', zh: '中文', fr: 'FR' }
  return (
    <header className="sc-hdr">
      <div className="sc-hdr-l">
        <a className="sc-brand" href="/" title={t.backWww}>
          <ScLogo />
          <span className="sc-wm">whereq<span className="sc-dot">.</span>com</span>
        </a>
        <span className="sc-sub-pill">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 10-10-5L2 10l10 5 10-5z" /><path d="M6 12v5c0 1 2.7 3 6 3s6-2 6-3v-5" /></svg>
          {t.brand}
        </span>
      </div>
      <div className="sc-hdr-c">
        <div className="sc-mode">
          <button className={mode === 'map' ? 'on' : ''} onClick={() => setMode('map')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="m9 4 6 2 6-2v14l-6 2-6-2-6 2V6z" /><path d="M9 4v14M15 6v14" /></svg>
            {t.modeMap}
          </button>
          <button className={mode === 'list' ? 'on' : ''} onClick={() => setMode('list')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" /></svg>
            {t.modeList}
          </button>
        </div>
      </div>
      <div className="sc-hdr-r">
        <a className="sc-back-www" href="/">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M11 18l-6-6 6-6" /></svg>
          {t.backWww}
        </a>
        <div className="sc-locale">
          <button className="sc-locale-btn" onClick={() => setLopen(!lopen)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" /></svg>
            <span style={{ textTransform: 'uppercase', fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '.08em' }}>{locale === 'zh' ? 'CN' : locale}</span>
          </button>
          {lopen && (
            <div className="sc-locale-menu">
              {(['en', 'zh', 'fr'] as ScLocale[]).map((c) => (
                <button key={c} className={locale === c ? 'on' : ''} onClick={() => { setLocale(c); setLopen(false) }}>{names[c]}</button>
              ))}
            </div>
          )}
        </div>
        <button className="sc-iconbtn" onClick={toggleTheme} title="Theme">
          {theme === 'dark'
            ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
            : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>}
        </button>
        <button className={`sc-iconbtn${isAuthenticated ? ' sc-iconbtn-on' : ''}`} title={accountTitle} onClick={onAccount}>
          {isAuthenticated && avatar
            ? <img className="sc-avatar" src={avatar} alt="" referrerPolicy="no-referrer" />
            : isAuthenticated
              ? <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><circle cx="9" cy="10" r=".9" fill="currentColor" stroke="none" /><circle cx="15" cy="10" r=".9" fill="currentColor" stroke="none" /></svg>
              : <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" /><path d="M9 10h.01M15 10h.01M8.5 15h7" /></svg>}
        </button>
      </div>
    </header>
  )
}

export function SchoolsPage() {
  const { theme, toggleTheme } = useTheme()
  const { i18n } = useTranslation()
  const { isAuthenticated, user, login, logout } = useAuth()
  const locale = scLocale(i18n.language)
  const setLocale = (l: ScLocale) => i18n.changeLanguage(l)
  const t = SC_I18N[locale]

  const [mode, setMode] = useState<'map' | 'list'>('map')
  const [filters, setFilters] = useState<SchoolFilters>(EMPTY_FILTERS)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<SchoolDetailT | null>(null)
  const [detail, setDetail] = useState<SchoolDetailT | null>(null)
  const [tax, setTax] = useState<Taxonomy | null>(null)
  const [showBoundary, setShowBoundary] = useState(true)
  const [cluster, setCluster] = useState(true)
  const [center, setCenter] = useState(TORONTO)
  const [locStatus, setLocStatus] = useState<'idle' | 'locating' | 'located' | 'fallback'>('idle')
  const [atHits, setAtHits] = useState<CatchmentHit[] | null>(null)
  const [atGated, setAtGated] = useState(false)
  // Explicit "Search" relocates the map to the extent of the matching schools.
  const [focusBounds, setFocusBounds] = useState<[number, number, number, number] | null>(null)
  const [focusNonce, setFocusNonce] = useState(0)

  const [page, setPage] = useState(0)
  const [per, setPer] = useState(25)
  const [sort, setSort] = useState<SortState>({ key: 'name', order: 'asc' })
  const [data, setData] = useState<PaginatedSchools | null>(null)
  const [loading, setLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<SchoolSummary[]>([])

  useEffect(() => { schoolsApi.taxonomy().then(setTax).catch(() => {}) }, [])
  useEffect(() => { setPage(0) }, [filters, query, per, sort])

  // geolocation → center the map (fallback Toronto)
  useEffect(() => {
    if (!navigator.geolocation) { setLocStatus('fallback'); return }
    setLocStatus('locating')
    const timer = setTimeout(() => setLocStatus((s) => (s === 'locating' ? 'fallback' : s)), 6000)
    navigator.geolocation.getCurrentPosition(
      (pos) => { clearTimeout(timer); setCenter({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setLocStatus('located') },
      () => { clearTimeout(timer); setLocStatus('fallback') },
      { timeout: 5500 },
    )
    return () => clearTimeout(timer)
  }, [])

  // main results query (drives the list table)
  const reqId = useRef(0)
  useEffect(() => {
    const id = ++reqId.current
    setLoading(true)
    schoolsApi.list({ filters, q: query, sort: sort.key, order: sort.order, page: page + 1, page_size: per })
      .then((d) => { if (id === reqId.current) setData(d) })
      .catch(() => {})
      .finally(() => { if (id === reqId.current) setLoading(false) })
  }, [filters, query, sort, page, per])

  // suggestions (debounced)
  useEffect(() => {
    const q = query.trim()
    if (!q) { setSuggestions([]); return }
    const h = setTimeout(() => {
      schoolsApi.list({ filters, q, page: 1, page_size: 12, rank: true }).then((d) => setSuggestions(d.items)).catch(() => {})
    }, 180)
    return () => clearTimeout(h)
  }, [query, filters])

  const selectId = (id: number) => { schoolsApi.detail(id).then((d) => { setSelected(d); setAtHits(null) }).catch(() => {}) }
  const pickSchool = (s: SchoolSummary) => { selectId(s.id) }
  const openDetail = (s: SchoolSummary) => { schoolsApi.detail(s.id).then(setDetail).catch(() => {}) }
  const onSort = (key: string) => setSort((s) => ({ key, order: s.key === key && s.order === 'asc' ? 'desc' : 'asc' }))

  // Apply the current name + filter criteria and fly the map to the result area.
  // (List/table already update live as criteria change; this is what relocates
  // the map — e.g. picking a school board jumps the map to that board's region.)
  const runSearch = () => {
    setMode('map')
    setPage(0)
    schoolsApi.mapPins({ filters, q: query, limit: 8000 })
      .then((pins) => {
        const loc = pins.filter((p) => p.lat != null && p.lng != null)
        if (!loc.length) return
        const lats = loc.map((p) => p.lat), lngs = loc.map((p) => p.lng)
        setFocusBounds([Math.min(...lats), Math.min(...lngs), Math.max(...lats), Math.max(...lngs)])
        setFocusNonce((n) => n + 1)
      })
      .catch(() => {})
  }

  const accountTitle = isAuthenticated
    ? [user?.displayName, t.auth.signOut].filter(Boolean).join(' · ')
    : t.auth.signIn
  const onAccount = () => (isAuthenticated ? logout() : login())
  const headerProps = {
    t, locale, setLocale, theme, toggleTheme, mode, setMode,
    isAuthenticated, avatar: user?.avatar, accountTitle, onAccount,
  }

  if (detail) {
    const viewOnMap = (s: SchoolDetailT) => { setDetail(null); setMode('map'); selectId(s.id) }
    return (
      <div className="sc-root">
        <Header {...headerProps} />
        <SchoolDetail t={t} school={detail} onBack={() => setDetail(null)} onViewMap={viewOnMap} />
      </div>
    )
  }

  return (
    <div className="sc-root">
      <Header {...headerProps} />
      {mode === 'map' ? (
        <div className="sc-maproot">
          <div className="sc-mapsearch">
            <SearchBox t={t} query={query} setQuery={setQuery} suggestions={suggestions} onPick={pickSchool} onSubmit={runSearch} />
            <Filters t={t} f={filters} setF={setFilters} tax={tax} compact onSearch={runSearch} />
            <div className="sc-mapsettings">
              {isAuthenticated ? (
                <label className="sc-toggle">
                  <input type="checkbox" checked={showBoundary} onChange={(e) => setShowBoundary(e.target.checked)} />
                  <span className="sc-toggle-tr" /><span className="sc-toggle-lbl">{t.showBoundary}</span>
                </label>
              ) : (
                <button type="button" className="sc-signin-link" onClick={login} title={t.auth.boundaryGated}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
                  {t.auth.boundaryGated}
                </button>
              )}
              <label className="sc-toggle">
                <input type="checkbox" checked={cluster} onChange={(e) => setCluster(e.target.checked)} />
                <span className="sc-toggle-tr" /><span className="sc-toggle-lbl">{t.clusterToggle}</span>
              </label>
              <span className="sc-locflag">
                <span className={`sc-loc-dot ${locStatus}`} />
                {locStatus === 'located' ? t.loc.you : locStatus === 'locating' ? t.loc.locating : t.loc.toronto}
              </span>
            </div>
            {atGated && (
              <div className="sc-athits">
                <div className="sc-athits-hd">{t.atHere}
                  <button onClick={() => setAtGated(false)} aria-label="close">×</button>
                </div>
                <div className="sc-athits-empty">{t.auth.catchmentGated}</div>
                <button className="sc-signin-link" style={{ margin: '0 10px 10px' }} onClick={login}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
                  {t.auth.signIn}
                </button>
              </div>
            )}
            {atHits && (
              <div className="sc-athits">
                <div className="sc-athits-hd">{t.atHere} · {atHits.length}
                  <button onClick={() => setAtHits(null)} aria-label="close">×</button>
                </div>
                {atHits.length === 0 && <div className="sc-athits-empty">{t.atHereHint}</div>}
                {atHits.map((h) => (
                  <button key={`${h.id}-${h.polygon_index}`} className="sc-athits-row" onClick={() => selectId(h.id)}>
                    <span>{h.name}</span><span className="sc-athits-meta">{h.type ?? ''}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="sc-mapsplit">
            <SchoolMap t={t} theme={theme} filters={filters} query={query} selected={selected}
              showBoundary={showBoundary && isAuthenticated} cluster={cluster} center={center}
              canBoundary={isAuthenticated} onGated={() => { setAtHits(null); setAtGated(true) }}
              focusBounds={focusBounds} focusNonce={focusNonce}
              onSelect={selectId} onAtPoint={(hits) => { setAtGated(false); setAtHits(hits) }} />
            <InfoPanel t={t} school={selected} onOpenDetail={openDetail} onClose={() => setSelected(null)} />
          </div>
        </div>
      ) : (
        <div className="sc-listroot sc-scroll">
          <div className="sc-listinner">
            <div className="sc-listsearch">
              <SearchBox t={t} query={query} setQuery={setQuery} suggestions={suggestions} onPick={(s) => { setQuery(s.name); openDetail(s) }} onSubmit={runSearch} />
              <Filters t={t} f={filters} setF={setFilters} tax={tax} onSearch={runSearch} />
            </div>
            <SchoolTable
              t={t} rows={data?.items ?? []} total={data?.total ?? 0} page={page} per={per} sort={sort}
              loading={loading} onOpen={openDetail} onSort={onSort} onPage={setPage} onPer={setPer}
            />
          </div>
        </div>
      )}
    </div>
  )
}
