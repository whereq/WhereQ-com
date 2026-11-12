import type { ScStrings } from '../i18n'
import type { SchoolSummary } from '../types'
import { schoolColor } from '../colors'
import { Stars, TypeBadges } from './shared'

export interface SortState { key: string; order: 'asc' | 'desc' }

function pageButtons(cur: number, pages: number): (number | '…')[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i)
  const out: (number | '…')[] = [0]
  const lo = Math.max(1, cur - 1), hi = Math.min(pages - 2, cur + 1)
  if (lo > 1) out.push('…')
  for (let i = lo; i <= hi; i++) out.push(i)
  if (hi < pages - 2) out.push('…')
  out.push(pages - 1)
  return out
}

export function SchoolTable({ t, rows, total, page, per, sort, loading, onOpen, onSort, onPage, onPer }: {
  t: ScStrings; rows: SchoolSummary[]; total: number; page: number; per: number; sort: SortState
  loading?: boolean
  onOpen: (s: SchoolSummary) => void
  onSort: (key: string) => void
  onPage: (p: number) => void
  onPer: (n: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / per))
  const cur = Math.min(page, pages - 1)

  const Th = ({ k, label, num, sortable }: { k?: string; label: string; num?: boolean; sortable?: boolean }) => (
    <th className={num ? 'num' : ''} onClick={() => sortable && k && onSort(k)} style={{ cursor: sortable ? 'pointer' : 'default' }}>
      {label}{sortable && sort.key === k && <span className="sc-sort">{sort.order === 'asc' ? '▲' : '▼'}</span>}
    </th>
  )

  return (
    <div className="sc-table-wrap">
      <table className="sc-table">
        <thead>
          <tr>
            <Th k="name" label={t.table.name} sortable />
            <Th label={t.table.type} />
            <Th label={t.table.board} />
            <Th label={t.table.region} />
            <Th k="hs_score" label={t.table.score} num sortable />
            <Th k="hs_rank" label={t.table.rank} num sortable />
            <Th k="grade_range" label={t.table.grades} sortable />
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} onClick={() => onOpen(s)}>
              <td className="sc-td-name"><span className="sc-dot" style={{ background: schoolColor({ type: s.type, board_type: s.board?.type, programs: s.programs }) }} />{s.name}</td>
              <td><TypeBadges school={s} /></td>
              <td className="sc-muted">{s.board?.name ?? '—'}</td>
              <td className="sc-muted">{s.region ?? s.province ?? '—'}</td>
              <td className="num"><Stars rating={s.hs_score} /></td>
              <td className="sc-muted num">{s.hs_rank != null ? `${s.hs_rank}${s.hs_rank_total ? '/' + s.hs_rank_total : ''}` : '—'}</td>
              <td className="sc-muted num">{s.grade_range ?? '—'}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={7} className="sc-empty">{loading ? '…' : t.noResults}</td></tr>}
        </tbody>
      </table>

      <div className="sc-pager">
        <div className="sc-pager-l">
          <span className="sc-pager-count">{total.toLocaleString()} {t.results}</span>
          <span className="sc-per">
            {[10, 25, 50].map((n) => (
              <button key={n} className={per === n ? 'on' : ''} onClick={() => onPer(n)}>{n}</button>
            ))}
            <span className="sc-per-lbl">{t.rows}</span>
          </span>
        </div>
        <div className="sc-pager-r">
          <button disabled={cur === 0} onClick={() => onPage(cur - 1)}>{t.prev}</button>
          <span className="sc-pager-pages">
            {pageButtons(cur, pages).map((p, i) => p === '…'
              ? <span key={i} className="sc-pg-dots">…</span>
              : <button key={i} className={p === cur ? 'on' : ''} onClick={() => onPage(p)}>{p + 1}</button>)}
          </span>
          <button disabled={cur >= pages - 1} onClick={() => onPage(cur + 1)}>{t.next}</button>
        </div>
      </div>
    </div>
  )
}
