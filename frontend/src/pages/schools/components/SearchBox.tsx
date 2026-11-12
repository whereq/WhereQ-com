import { useEffect, useRef, useState } from 'react'
import type { ScStrings } from '../i18n'
import type { SchoolSummary } from '../types'
import { schoolColor } from '../colors'

export function SearchBox({ t, query, setQuery, suggestions, onPick, onSubmit }: {
  t: ScStrings; query: string; setQuery: (q: string) => void
  suggestions: SchoolSummary[]; onPick: (s: SchoolSummary) => void; onSubmit?: () => void
}) {
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(0)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const fn = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', fn)
    return () => document.removeEventListener('mousedown', fn)
  }, [])
  useEffect(() => { setHi(0) }, [query])

  const show = open && query.trim().length > 0 && suggestions.length > 0
  const pick = (s: SchoolSummary) => { onPick(s); setOpen(false) }

  return (
    <div className="sc-search-wrap" ref={ref}>
      <div className="sc-search">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input
          value={query}
          placeholder={t.searchPh}
          onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (show) {
              if (e.key === 'ArrowDown') { e.preventDefault(); setHi((h) => Math.min(h + 1, suggestions.length - 1)) }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)) }
              else if (e.key === 'Enter') { e.preventDefault(); pick(suggestions[hi]) }
              else if (e.key === 'Escape') setOpen(false)
              return
            }
            // No suggestion list open → Enter submits the current criteria.
            if (e.key === 'Enter') { e.preventDefault(); setOpen(false); onSubmit?.() }
          }}
        />
        {query && (
          <button className="sc-search-x" onClick={() => { setQuery(''); setOpen(false) }} aria-label="clear">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        )}
      </div>
      {show && (
        <div className="sc-suggest sc-scroll">
          {suggestions.map((s, i) => (
            <button key={s.id} className={`sc-sug ${i === hi ? 'hi' : ''}`} onMouseEnter={() => setHi(i)} onClick={() => pick(s)}>
              <span className="sc-sug-dot" style={{ background: schoolColor({ type: s.type, board_type: s.board?.type, programs: s.programs }) }} />
              <span className="sc-sug-main">
                <span className="sc-sug-name">{s.name}</span>
                <span className="sc-sug-sub">{s.board?.name ?? ''}{s.city ? ` · ${s.city}` : ''}</span>
              </span>
              <span className="sc-sug-type">{s.type ?? ''}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
