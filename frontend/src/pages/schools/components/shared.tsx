import { schoolBadges, schoolColor } from '../colors'
import type { SchoolSummary } from '../types'

export function Stars({ rating }: { rating: number | null }) {
  if (rating == null) return <span className="sc-rating"><span className="none">—</span></span>
  const pct = (rating / 10) * 100
  return (
    <span className="sc-rating">
      <span className="sc-rating-bar"><span className="sc-rating-fill" style={{ width: pct + '%' }} /></span>
      <b>{rating.toFixed(1)}</b>
    </span>
  )
}

export function TypeBadges({ school }: { school: Pick<SchoolSummary, 'type' | 'programs' | 'board'> }) {
  const badges = schoolBadges({ type: school.type, board_type: school.board?.type, programs: school.programs })
  return (
    <span className="sc-badges">
      {badges.map((b) => (
        <span key={b.code} className="sc-badge" style={{ ['--bc' as string]: b.color }}>{b.label}</span>
      ))}
    </span>
  )
}

export function Crest({ name, color }: { name: string; color: string }) {
  const initials = name.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w)).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
  return (
    <div className="sc-crest" style={{ background: `linear-gradient(135deg, ${color}, ${color}99)` }}>
      <span>{initials || 'S'}</span>
    </div>
  )
}

export function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="sc-kv-row"><span className="sc-kv-k">{k}</span><span className="sc-kv-v">{v}</span></div>
}

export { schoolColor }
