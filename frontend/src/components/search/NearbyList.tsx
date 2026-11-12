import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { nearbyApi } from '@/lib/nearbyApi'
import {
  DEFAULT_RADIUS_KM,
  NEARBY_CATEGORIES,
  NEARBY_CATEGORY_IDS,
  toggleCategorySelection,
} from '@/lib/nearbyCategories'
import { RadiusPicker } from '@/components/ui/RadiusPicker'
import { useUserSettings } from '@/hooks/useUserSettings'
import type { NearbyItem, NearbyResponse } from '@/types/nearby'

interface Props {
  /** The map centre — the nearby search is centred on it. */
  center: { lat: number; lng: number } | null
  /** The text typed in the search box — it narrows the nearby list. */
  query: string
  /** A row was picked — the caller opens that place's card. */
  onSelectItem: (item: NearbyItem) => void
  /**
   * Controlled mode. A card carries its **own** radius and categories — they
   * are part of the card, not of the account — so the list can be driven by
   * the caller instead of by the account's settings. When these two are
   * given, the caller owns the edits (through the two callbacks below); when
   * they are not, the list reads and writes the account's own settings, which
   * is how the map and the search modal use it.
   */
  radiusKm?: number
  categories?: string[]
  onRadiusChange?: (km: number) => void
  onCategoriesChange?: (categories: string[]) => void
}

/** A stable empty selection — the identity of "every category". */
const EMPTY: string[] = []

/** "450 m" / "1.2 km" */
function formatDistance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres)} m`
  return `${(metres / 1000).toFixed(1)} km`
}

/** The second line of a row: price, distance, and whatever the source knows. */
function itemMeta(item: NearbyItem, when?: string): string {
  const bits: string[] = []
  if (item.price != null) bits.push(`${item.price.toFixed(2)} ${item.currency ?? ''}`.trim())
  bits.push(formatDistance(item.distance_m))
  if (item.meta) bits.push(item.meta)
  if (when) bits.push(when)
  return bits.join(' · ')
}

/**
 * The nearby list: everything around the map centre within the chosen radius —
 * the POIs, the fuel stations, the news and the schools — filterable by the
 * categories the map already uses.
 *
 * The radius and the categories are the user's own settings, so they are kept
 * on the account (and in the browser while they are signed out).
 */
export function NearbyList({
  center, query, onSelectItem,
  radiusKm, categories, onRadiusChange, onCategoriesChange,
}: Props) {
  const { t } = useTranslation()
  const { settings, update } = useUserSettings()
  const [data, setData] = useState<NearbyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  // Controlled (a card's own radius and categories) or the account's settings.
  const controlled = radiusKm !== undefined && categories !== undefined
  const effRadius: number = controlled ? (radiusKm ?? DEFAULT_RADIUS_KM) : settings.radiusKm
  const effCategories: string[] = (controlled ? categories : settings.categories) ?? EMPTY

  // An empty selection means every category.
  const selected = useMemo(
    () => (effCategories.length ? effCategories : NEARBY_CATEGORY_IDS),
    [effCategories],
  )
  const selectedKey = effCategories.join(',')

  useEffect(() => {
    if (!center) return
    let cancelled = false
    setLoading(true)
    setError(false)
    nearbyApi
      .list({
        lat: center.lat,
        lng: center.lng,
        radiusKm: effRadius,
        categories: effCategories,
        limit: 100,
      })
      .then(res => {
        if (!cancelled) setData(res)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [center?.lat, center?.lng, effRadius, selectedKey])

  // The typed text narrows the list on top of the category filter.
  const items = useMemo(() => {
    const list = data?.items ?? []
    const q = query.trim().toLowerCase()
    if (!q) return list
    return list.filter(
      i =>
        i.name.toLowerCase().includes(q) ||
        (i.meta ?? '').toLowerCase().includes(q) ||
        i.category.toLowerCase().includes(q),
    )
  }, [data, query])

  const toggleCategory = (id: string) => {
    const next = toggleCategorySelection(effCategories, id)
    // The last one cannot be switched off: an empty selection *is* "every
    // category", so there is no "nothing at all" state.
    if (!next) return
    if (controlled) onCategoriesChange?.(next)
    else update({ categories: next })
  }

  const setRadius = (km: number) => {
    if (controlled) onRadiusChange?.(km)
    else update({ radiusKm: km })
  }

  if (!center) {
    return <div className="search-modal-status">{t('nearby.noCentre')}</div>
  }

  return (
    <>
      <div className="nearby-section">
        <span className="nearby-label">{t('nearby.radius')}</span>
        <RadiusPicker value={effRadius} onChange={setRadius} />
      </div>

      <div className="nearby-section">
        <span className="nearby-label">{t('nearby.categories')}</span>
        <div className="chip-rail">
          <button
            className={`chip-xs${selected.length === NEARBY_CATEGORY_IDS.length ? ' on' : ''}`}
            onClick={() => update({ categories: [] })}
          >
            {t('nearby.all')}
          </button>
          {NEARBY_CATEGORIES.map(cat => {
            const on = selected.includes(cat.id)
            const count = data?.counts?.[cat.id] ?? 0
            return (
              <button
                key={cat.id}
                className={`chip-xs${on ? ' on' : ''}`}
                onClick={() => toggleCategory(cat.id)}
                title={t(cat.labelKey)}
              >
                <span className="chip-dot" style={{ background: cat.color }} />
                {t(cat.labelKey)}
                {count > 0 && <span className="chip-count">{count}</span>}
              </button>
            )
          })}
        </div>
      </div>

      <div className="search-modal-results">
        {loading && <div className="search-modal-status">{t('nearby.loading')}</div>}
        {!loading && error && <div className="search-modal-status">{t('nearby.error')}</div>}
        {!loading && !error && items.length === 0 && (
          <div className="search-modal-status">{t('nearby.empty')}</div>
        )}
        {!loading &&
          !error &&
          items.map(item => (
            <button
              key={item.id}
              className="search-modal-item"
              onClick={() => onSelectItem(item)}
            >
              <span
                className="search-modal-dot"
                style={{
                  background:
                    NEARBY_CATEGORIES.find(c => c.id === item.category)?.color ??
                    'var(--muted)',
                }}
              />
              <span className="search-modal-name">{item.name}</span>
              <span className="search-modal-meta">
                {itemMeta(item, item.when ? t('nearby.recent') : undefined)}
              </span>
            </button>
          ))}
        {!loading && !error && items.length > 0 && (
          <div className="nearby-foot">{t('nearby.count', { count: items.length })}</div>
        )}
      </div>
    </>
  )
}
