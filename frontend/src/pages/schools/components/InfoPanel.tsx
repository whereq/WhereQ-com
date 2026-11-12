import type { ScStrings } from '../i18n'
import type { SchoolSummary } from '../types'
import { schoolColor } from '../colors'
import { Crest, Row, Stars, TypeBadges } from './shared'

export function InfoPanel({ t, school, onOpenDetail, onClose }: {
  t: ScStrings; school: SchoolSummary | null; onOpenDetail: (s: SchoolSummary) => void; onClose: () => void
}) {
  if (!school) {
    return (
      <div className="sc-info empty">
        <div className="sc-info-empty">
          <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M12 21s7-6.5 7-11a7 7 0 1 0-14 0c0 4.5 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></svg>
          <div className="sc-info-empty-t">{t.selectSchool}</div>
          <div className="sc-info-empty-s">{t.selectHint}</div>
        </div>
      </div>
    )
  }
  const c = schoolColor({ type: school.type, board_type: school.board?.type, programs: school.programs })
  return (
    <div className="sc-info">
      <div className="sc-info-hd" style={{ ['--c' as string]: c }}>
        <Crest name={school.name} color={c} />
        <button className="sc-info-x" onClick={onClose}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
        </button>
      </div>
      <div className="sc-info-body sc-scroll">
        <h3 className="sc-info-name">{school.name}</h3>
        <TypeBadges school={school} />
        <div className="sc-info-rating"><Stars rating={school.hs_score} /></div>
        <div className="sc-kv">
          <Row k={t.detail.board} v={school.board?.name ?? '—'} />
          <Row k={t.detail.grades} v={school.grade_range ?? '—'} />
          <Row k={t.detail.rank} v={school.hs_rank != null ? `${school.hs_rank}${school.hs_rank_total ? '/' + school.hs_rank_total : ''}` : '—'} />
          <Row k={t.detail.boardType} v={school.board?.type ? school.board.type[0].toUpperCase() + school.board.type.slice(1) : '—'} />
          <Row k={t.detail.region} v={school.region ?? school.province ?? '—'} />
        </div>
        <div className={`sc-bd-flag ${school.has_boundary ? 'yes' : 'no'}`}>
          <span className="sc-bd-dot" />{school.has_boundary ? t.detail.boundaryYes : t.detail.boundaryNo}
        </div>
        {school.city && (
          <div className="sc-info-addr">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 21s7-6.5 7-11a7 7 0 1 0-14 0c0 4.5 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></svg>
            {school.city}
          </div>
        )}
        <button className="sc-info-cta" onClick={() => onOpenDetail(school)}>{t.detail.overview} →</button>
      </div>
    </div>
  )
}
