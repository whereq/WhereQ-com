import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { localApi } from '@/lib/localApi'
import { Button } from '@/components/ui/Button'
import { categoryColor } from './localMarkers'
import type { LocalTaxonomy } from '@/types/local'

export type RangeKey = '24h' | '7d' | '30d' | 'all'

const TYPES: { id: string; key: string }[] = [
  { id: 'news', key: 'local.news' },
  { id: 'event', key: 'local.events' },
  { id: 'story', key: 'local.stories' },
  { id: 'topic', key: 'local.topics' },
]

interface Props {
  types: string[]; setTypes: (t: string[]) => void
  categories: string[]; setCategories: (c: string[]) => void
  sources: string[]; setSources: (s: string[]) => void
  range: RangeKey; setRange: (r: RangeKey) => void
  count: number; capped: boolean
}

function toggle(list: string[], v: string): string[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
}

export function LocalContentControls({
  types, setTypes, categories, setCategories, sources, setSources, range, setRange, count, capped,
}: Props) {
  const { t } = useTranslation()
  const [tax, setTax] = useState<LocalTaxonomy | null>(null)
  const [expanded, setExpanded] = useState(false)
  const on = types.length > 0

  useEffect(() => { localApi.taxonomy().then(setTax).catch(() => {}) }, [])

  const ranges: RangeKey[] = ['24h', '7d', '30d', 'all']

  return (
    <div style={{
      background: 'var(--surface, #11161D)', border: '1px solid var(--border, #232B36)',
      borderRadius: 'var(--r-md, 4px)', padding: 12, width: 248, boxShadow: 'var(--shadow-2)',
      fontFamily: 'var(--font-body, system-ui, sans-serif)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{
          fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.08em',
          color: 'var(--text-2, #94A2B5)',
        }}>{t('local.title')}</span>
        {on && (
          <Button variant="ghost" size="sm" onClick={() => setTypes([])}>{t('local.clear')}</Button>
        )}
      </div>

      {/* Type toggles — shared chip rail (matches QUICK CATEGORIES) */}
      <div className="chips" style={{ marginBottom: on ? 10 : 0 }}>
        {TYPES.map(({ id, key }) => (
          <Button key={id} variant="chip" selected={types.includes(id)}
            onClick={() => setTypes(toggle(types, id))}>{t(key)}</Button>
        ))}
      </div>

      {on && (
        <>
          {/* Time range */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
            {ranges.map((r) => (
              <Button key={r} variant="outline" size="sm" selected={range === r}
                onClick={() => setRange(r)} style={{ flex: 1 }}>
                {t(`local.range.${r}`)}
              </Button>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            fontSize: 11, color: 'var(--muted, #6A7382)', marginBottom: expanded ? 8 : 0 }}>
            <span>{capped ? t('local.zoomHint') : t('local.results', { count })}</span>
            <Button variant="ghost" size="sm" onClick={() => setExpanded((e) => !e)}>
              {expanded ? t('local.less') : t('local.more')}
            </Button>
          </div>

          {expanded && tax && (
            <div style={{ maxHeight: 220, overflowY: 'auto', marginTop: 4 }}>
              {tax.categories.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.06em',
                    color: 'var(--muted, #6A7382)', margin: '4px 0' }}>{t('local.category')}</div>
                  {tax.categories.map((c) => (
                    <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0',
                      fontSize: 12, color: 'var(--text, #D4DDE8)', cursor: 'pointer' }}>
                      <input type="checkbox" checked={categories.includes(c.id)}
                        onChange={() => setCategories(toggle(categories, c.id))} />
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: categoryColor(c.id) }} />
                      <span style={{ flex: 1 }}>{c.name}</span>
                      <span style={{ color: 'var(--muted, #6A7382)' }}>{c.count}</span>
                    </label>
                  ))}
                </div>
              )}
              {tax.sources.length > 0 && (
                <div>
                  <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.06em',
                    color: 'var(--muted, #6A7382)', margin: '4px 0' }}>{t('local.source')}</div>
                  {tax.sources.map((s) => (
                    <label key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0',
                      fontSize: 12, color: 'var(--text, #D4DDE8)', cursor: 'pointer' }}>
                      <input type="checkbox" checked={sources.includes(s.slug)}
                        onChange={() => setSources(toggle(sources, s.slug))} />
                      <span style={{ flex: 1 }}>{s.name}</span>
                      <span style={{ color: 'var(--muted, #6A7382)' }}>{s.count}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
