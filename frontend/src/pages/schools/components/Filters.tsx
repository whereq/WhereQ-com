import type { ScStrings } from '../i18n'
import type { SchoolFilters, TaxItem, Taxonomy } from '../types'
import { EMPTY_FILTERS } from '../types'

function Chevron() {
  return (
    <svg className="sc-select-ic" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
  )
}

function Select({ label, value, onChange, options, anyLabel, disabled }: {
  label: string; value: string; onChange: (v: string) => void; options: TaxItem[]; anyLabel: string; disabled?: boolean
}) {
  return (
    <label className={`sc-field ${disabled ? 'dis' : ''}`}>
      <span className="sc-field-l">{label}</span>
      <div className="sc-select">
        <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
          <option value="">{anyLabel}</option>
          {options.map((o) => (
            <option key={o.id} value={o.id} disabled={o.enabled === false}>
              {o.name}{o.enabled === false ? ' · soon' : ''}
            </option>
          ))}
        </select>
        <Chevron />
      </div>
    </label>
  )
}

export function Filters({ t, f, setF, tax, compact, onSearch }: {
  t: ScStrings; f: SchoolFilters; setF: (f: SchoolFilters) => void; tax: Taxonomy | null
  compact?: boolean; onSearch?: () => void
}) {
  const provinces = tax?.provinces ?? []
  // Board is the primary org filter; Region/Board-Type were redundant with it
  // and have been removed from the UI. Boards are scoped by province only.
  const boards: TaxItem[] = (tax?.boards ?? [])
    .filter((b) => !f.province || b.province === f.province)
    .map((b) => ({ id: b.slug, name: b.name }))
  const types = tax?.types ?? []
  const programs = tax?.programs ?? []

  const set = (k: keyof SchoolFilters, v: string) => {
    const next = { ...f, [k]: v }
    // Changing province invalidates the dependent board selection.
    if (k === 'province') { next.region = ''; next.board = '' }
    setF(next)
  }
  const active = (['province', 'board', 'type', 'program'] as const).filter((k) => f[k]).length

  return (
    <div className={`sc-filters ${compact ? 'compact' : ''}`}>
      <Select label={t.f.province} value={f.province} onChange={(v) => set('province', v)} options={provinces} anyLabel={t.f.any} />
      <Select label={t.f.board} value={f.board} onChange={(v) => set('board', v)} options={boards} anyLabel={t.f.any} disabled={!boards.length} />
      <Select label={t.f.type} value={f.type} onChange={(v) => set('type', v)} options={types} anyLabel={t.f.any} />
      <Select label={t.f.program} value={f.program} onChange={(v) => set('program', v)} options={programs} anyLabel={t.f.any} />
      {active > 0 && (
        <button className="sc-clear" onClick={() => setF({ ...EMPTY_FILTERS, country: f.country, province: f.province })}>
          {t.clear} <span className="sc-clear-n">{active}</span>
        </button>
      )}
      {onSearch && (
        <button className="sc-search-go" onClick={onSearch} title={t.searchGo}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          {t.searchGo}
        </button>
      )}
    </div>
  )
}
