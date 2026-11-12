import type { ScStrings } from '../i18n'
import type { GeoMultiPolygon, SchoolDetail as SchoolDetailT } from '../types'
import { programLabel, schoolColor } from '../colors'
import { Crest, Row, TypeBadges } from './shared'

function CatchmentPreview({ geo, color }: { geo: GeoMultiPolygon; color: string }) {
  // outer ring of the first polygon, normalized into a 100×100 box
  const ring = geo.coordinates[0]?.[0] ?? []
  if (ring.length < 3) return null
  const lngs = ring.map((p) => p[0]), lats = ring.map((p) => p[1])
  const minLng = Math.min(...lngs), maxLng = Math.max(...lngs), minLat = Math.min(...lats), maxLat = Math.max(...lats)
  const pts = ring.map((p) => {
    const x = 8 + 84 * ((p[0] - minLng) / (maxLng - minLng || 1))
    const y = 8 + 84 * (1 - (p[1] - minLat) / (maxLat - minLat || 1))
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg viewBox="0 0 100 100" style={{ width: '100%', height: '100%' }}>
      <defs><pattern id="scgrid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" fill="none" stroke="var(--border-2)" strokeWidth="0.5" /></pattern></defs>
      <rect width="100" height="100" fill="url(#scgrid)" />
      <polygon points={pts} fill={color} fillOpacity="0.18" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

function RatingTrend({ scores }: { scores: SchoolDetailT['scores'] }) {
  const pts = scores.filter((s) => s.rank_score != null)
  if (!pts.length) return null
  const max = Math.max(...pts.map((s) => s.rank_score!))
  return (
    <div className="sc-trend">
      {pts.map((s) => (
        <div key={s.year} className="sc-trend-bar" title={`${s.year}: ${s.rank_score}`}>
          <div className="sc-trend-fill" style={{ height: `${(s.rank_score! / (max || 10)) * 100}%` }} />
          <span className="sc-trend-yr">{String(s.year).slice(2)}</span>
        </div>
      ))}
    </div>
  )
}

export function SchoolDetail({ t, school, onBack, onViewMap }: {
  t: ScStrings; school: SchoolDetailT; onBack: () => void; onViewMap: (s: SchoolDetailT) => void
}) {
  const c = schoolColor({ type: school.type, board_type: school.board?.type, programs: school.programs })
  return (
    <div className="sc-detail sc-scroll">
      <div className="sc-detail-inner">
        <button className="sc-detail-back" onClick={onBack}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M11 18l-6-6 6-6" /></svg>
          {t.detail.back}
        </button>

        <div className="sc-detail-hero">
          <Crest name={school.name} color={c} />
          <div className="sc-detail-head">
            <h1>{school.name}</h1>
            <div className="sc-detail-sub">{school.board?.name ?? ''}{school.region ? ` · ${school.region}` : ''}, {school.province}</div>
            <TypeBadges school={school} />
          </div>
          <div className="sc-detail-actions">
            {(() => {
              const hasLoc = school.lat != null && school.lng != null
              return (
                <button className="sc-da-primary" disabled={!hasLoc}
                  title={hasLoc ? undefined : t.detail.noLocation}
                  onClick={() => hasLoc && onViewMap(school)}>
                  {t.detail.viewOnMap}
                </button>
              )
            })()}
            {school.website_url && <a className="sc-da-ghost" href={school.website_url} target="_blank" rel="noreferrer">{t.detail.website}</a>}
          </div>
        </div>

        <div className="sc-detail-grid">
          <div className="sc-stat"><span className="sc-stat-k">{t.detail.score}</span><span className="sc-stat-v">{school.hs_score != null ? <>{school.hs_score.toFixed(1)}<small>/10</small></> : '—'}</span></div>
          <div className="sc-stat"><span className="sc-stat-k">{t.detail.rank}</span><span className="sc-stat-v">{school.hs_rank != null ? <>{school.hs_rank}<small>/{school.hs_rank_total ?? '—'}</small></> : '—'}</span></div>
          <div className="sc-stat"><span className="sc-stat-k">{t.detail.grades}</span><span className="sc-stat-v" style={{ fontSize: 15 }}>{school.grade_range ?? '—'}</span></div>
          <div className="sc-stat"><span className="sc-stat-k">{t.detail.boardType}</span><span className="sc-stat-v" style={{ fontSize: 15 }}>{school.board?.type ? school.board.type[0].toUpperCase() + school.board.type.slice(1) : '—'}</span></div>
        </div>

        <div className="sc-detail-cols">
          <section className="sc-sec">
            <h2>{t.detail.contact}</h2>
            <div className="sc-kv">
              {school.address && <Row k={t.detail.address} v={school.address} />}
              {school.phone && <Row k={t.detail.phone} v={school.phone} />}
              <Row k={t.detail.board} v={school.board?.name ?? '—'} />
              {school.programs.length > 0 && <Row k={t.detail.programs} v={school.programs.map(programLabel).join(' · ')} />}
            </div>
            {school.scores.some((s) => s.rank_score != null) && (
              <>
                <h2 style={{ marginTop: 18 }}>{t.detail.scoresTrend}</h2>
                <RatingTrend scores={school.scores} />
              </>
            )}
          </section>

          <section className="sc-sec">
            <h2>{t.detail.catchment}</h2>
            <div className="sc-catch-preview" style={{ ['--c' as string]: c }}>
              {school.boundary_geojson
                ? <CatchmentPreview geo={school.boundary_geojson} color={c} />
                : <div className="sc-catch-none">{t.detail.boundaryNo}</div>}
            </div>
            <div className={`sc-bd-flag ${school.has_boundary ? 'yes' : 'no'}`}>
              <span className="sc-bd-dot" />{school.has_boundary ? t.detail.boundaryYes : t.detail.boundaryNo}
            </div>
            {school.eqao.length > 0 && (
              <>
                <h2 style={{ marginTop: 14 }}>{t.detail.eqao}</h2>
                <div className="sc-kv">
                  {school.eqao.map((e) => (
                    <Row key={e.grade} k={`Grade ${e.grade}${e.year_mark ? ` · ${e.year_mark}` : ''}`}
                      v={e.rank != null ? `${e.rank}${e.total ? '/' + e.total : ''}` : '—'} />
                  ))}
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
