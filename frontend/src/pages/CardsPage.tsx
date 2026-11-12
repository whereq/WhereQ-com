import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/contexts/AuthContext'
import { usePlaceCards } from '@/hooks/usePlaceCards'
import { useSearch } from '@/hooks/useSearch'
import { NearbyList } from '@/components/search/NearbyList'
import { RadiusPicker } from '@/components/ui/RadiusPicker'
import {
  DEFAULT_RADIUS_KM,
  NEARBY_CATEGORIES,
  NEARBY_CATEGORY_IDS,
  formatRadius,
  toggleCategorySelection,
} from '@/lib/nearbyCategories'
import type { PlaceCardDTO, PlaceCardKind } from '@/types/placeCard'

/** The categories a business card can be labelled with. */
const BUSINESS_CATEGORIES = [
  'food', 'coffee', 'fuel', 'parking', 'stays',
  'pharmacy', 'clinic', 'library', 'plaza',
]

/** What the editor holds while it is open. */
interface Draft {
  id: number | null
  name: string
  description: string
  kind: PlaceCardKind
  category: string
  latitude: number | null
  longitude: number | null
  address: string
  radiusKm: number
  categories: string[]
  logoUrl: string
  accent: string
}

const emptyDraft = (): Draft => ({
  id: null,
  name: '',
  description: '',
  kind: 'business',
  category: '',
  latitude: null,
  longitude: null,
  address: '',
  radiusKm: DEFAULT_RADIUS_KM,
  categories: [],
  logoUrl: '',
  accent: '#4ADE80',
})

export function CardsPage() {
  const { t } = useTranslation()
  const { isAuthenticated, login } = useAuth()
  const { cards, loading, createCard, updateCard, deleteCard } = usePlaceCards()

  const [draft, setDraft] = useState<Draft | null>(null)
  const [viewing, setViewing] = useState<PlaceCardDTO | null>(null)
  const [addressQuery, setAddressQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The address picker is the app's own search: Google Places for streets and
  // addresses, our own places and schools for the rest.
  const { results, resolve } = useSearch(addressQuery, 280, !!draft)

  useEffect(() => {
    // The query is cleared when the editor closes, so it never shows the
    // previous search's text over a fresh card.
    if (!draft) setAddressQuery('')
  }, [draft])

  const selectedCount = useMemo(
    () => (draft?.categories.length ? draft.categories.length : NEARBY_CATEGORY_IDS.length),
    [draft?.categories],
  )

  if (!isAuthenticated) {
    return (
      <main className="content-page">
        <div className="content-page-inner">
          <div className="content-page-hd">
            <h1>{t('cards.title', 'My cards')}</h1>
            <p>{t('cards.subtitle', 'Your own card for a place — and what is around it.')}</p>
          </div>
          <div className="content-empty">
            <p>{t('cards.signinText', 'Sign in to make a card.')}</p>
            <button className="cards-btn" onClick={() => login()}>
              {t('signin')}
            </button>
          </div>
        </div>
      </main>
    )
  }

  const openNew = () => {
    setError(null)
    setDraft(emptyDraft())
  }

  const openEdit = (card: PlaceCardDTO) => {
    setError(null)
    setDraft({
      id: card.id,
      name: card.name,
      description: card.description ?? '',
      kind: card.kind,
      category: card.category ?? '',
      latitude: card.latitude,
      longitude: card.longitude,
      address: card.address ?? '',
      radiusKm: card.radius_km,
      categories: card.categories,
      logoUrl: card.logo_url ?? '',
      accent: card.accent ?? '#4ADE80',
    })
  }

  const pickAddress = async (id: string) => {
    const r = results.find(x => x.id === id)
    if (!r || !draft) return
    const coords = await resolve(r)
    if (!coords) {
      setError(t('cards.addressFailed', 'That address could not be resolved.'))
      return
    }
    setDraft({
      ...draft,
      name: draft.name || r.name,
      address: coords.address ?? r.meta,
      latitude: coords.lat,
      longitude: coords.lng,
    })
    setAddressQuery('')
  }

  const save = async () => {
    if (!draft) return
    if (!draft.name.trim()) {
      setError(t('cards.nameRequired', 'The card needs a name.'))
      return
    }
    if (draft.latitude == null || draft.longitude == null) {
      setError(t('cards.addressRequired', 'Search for the address the card is about.'))
      return
    }
    setBusy(true)
    setError(null)
    const body = {
      name: draft.name.trim(),
      description: draft.description.trim() || null,
      kind: draft.kind,
      category: draft.kind === 'business' ? draft.category || null : null,
      latitude: draft.latitude,
      longitude: draft.longitude,
      address: draft.address.trim() || null,
      radius_km: draft.radiusKm,
      categories: draft.categories,
      logo_url: draft.logoUrl.trim() || null,
      accent: draft.accent.trim() || null,
    }
    try {
      if (draft.id == null) await createCard(body)
      else await updateCard(draft.id, body)
      setDraft(null)
    } catch {
      setError(t('cards.saveFailed', 'The card could not be saved.'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (card: PlaceCardDTO) => {
    if (!window.confirm(t('cards.confirmDelete', 'Delete this card?'))) return
    try {
      await deleteCard(card.id)
      if (viewing?.id === card.id) setViewing(null)
    } catch {
      /* the shared fetch wrapper already reported it */
    }
  }

  const toggleCategory = (id: string) => {
    if (!draft) return
    const next = toggleCategorySelection(draft.categories, id)
    if (!next) return
    setDraft({ ...draft, categories: next })
  }

  return (
    <main className="content-page">
      <div className="content-page-inner">
        <div className="content-page-hd">
          <h1>{t('cards.title', 'My cards')}</h1>
          <p>{t('cards.subtitle', 'Your own card for a place — and what is around it.')}</p>
        </div>

        <div className="cards-toolbar">
          <button className="cards-btn" onClick={openNew}>
            {t('cards.new', 'New card')}
          </button>
          {cards.length > 0 && (
            <span className="cards-count">
              {t('cards.count', { count: cards.length })}
            </span>
          )}
        </div>

        {loading && <div className="content-empty">{t('cards.loading', 'Loading your cards...')}</div>}

        {!loading && cards.length === 0 && (
          <div className="content-empty">
            {t('cards.empty', 'No cards yet. Make one for a place you care about.')}
          </div>
        )}

        <div className="content-grid">
          {cards.map(card => (
            <div key={card.id} className="content-card cards-card">
              <div className="cards-card-top">
                {card.logo_url ? (
                  <img className="cards-logo" src={card.logo_url} alt="" referrerPolicy="no-referrer" />
                ) : (
                  <span className="cards-logo cards-logo-ph" style={{ background: card.accent ?? 'var(--accent)' }}>
                    {card.name.slice(0, 1).toUpperCase()}
                  </span>
                )}
                <div>
                  <h3>{card.name}</h3>
                  <div className="meta">
                    {card.kind === 'person'
                      ? t('cards.kindPerson', 'Person')
                      : card.category || t('cards.kindBusiness', 'Business')}
                    {card.address ? ` · ${card.address}` : ''}
                  </div>
                </div>
              </div>
              {card.description && <p>{card.description}</p>}
              <div className="meta">
                {t('cards.radius', 'Radius')} {formatRadius(card.radius_km)}
                {' · '}
                {card.categories.length
                  ? t('cards.categoryCount', { count: card.categories.length })
                  : t('cards.allCategories', 'every category')}
              </div>
              <div className="cards-card-acts">
                <button className="cards-btn ghost" onClick={() => setViewing(card)}>
                  {t('cards.view', 'Open')}
                </button>
                <button className="cards-btn ghost" onClick={() => openEdit(card)}>
                  {t('cards.edit', 'Edit')}
                </button>
                <button className="cards-btn ghost danger" onClick={() => void remove(card)}>
                  {t('cards.delete', 'Delete')}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── the card itself ─────────────────────────────────────────────── */}
      {viewing && (
        <div className="cards-overlay" onClick={() => setViewing(null)}>
          <div className="cards-modal cards-modal-wide" onClick={e => e.stopPropagation()}>
            <div className="cards-card-hero" style={{ borderColor: viewing.accent ?? 'var(--accent)' }}>
              {viewing.logo_url && (
                <img className="cards-logo lg" src={viewing.logo_url} alt="" referrerPolicy="no-referrer" />
              )}
              <div>
                <div className="cards-hero-kicker">
                  {viewing.kind === 'person'
                    ? t('cards.kindPerson', 'Person')
                    : viewing.category || t('cards.kindBusiness', 'Business')}
                </div>
                <h2>{viewing.name}</h2>
                {viewing.address && <div className="cards-hero-sub">{viewing.address}</div>}
                {viewing.description && <p>{viewing.description}</p>}
              </div>
            </div>
            <div className="place-nearby-hd">{t('search.nearbyAround', 'What is around it')}</div>
            <NearbyList
              center={{ lat: viewing.latitude, lng: viewing.longitude }}
              query=""
              radiusKm={viewing.radius_km}
              categories={viewing.categories}
              onSelectItem={() => { /* the card page has no map to fly to */ }}
            />
          </div>
        </div>
      )}

      {/* ── the editor ──────────────────────────────────────────────────── */}
      {draft && (
        <div className="cards-overlay" onClick={() => setDraft(null)}>
          <div className="cards-modal" onClick={e => e.stopPropagation()}>
            <h2 className="cards-modal-hd">
              {draft.id == null ? t('cards.new', 'New card') : t('cards.edit', 'Edit')}
            </h2>

            <label className="cards-field">
              <span>{t('cards.name', 'Name')}</span>
              <input
                value={draft.name}
                onChange={e => setDraft({ ...draft, name: e.target.value })}
                placeholder={t('cards.namePlaceholder', 'The name on the card')}
              />
            </label>

            <label className="cards-field">
              <span>{t('cards.description', 'Description')}</span>
              <textarea
                value={draft.description}
                onChange={e => setDraft({ ...draft, description: e.target.value })}
                rows={3}
                placeholder={t('cards.descriptionPlaceholder', 'What someone should know about it')}
              />
            </label>

            <div className="cards-field">
              <span>{t('cards.profile', 'Profile')}</span>
              <div className="chip-rail">
                <button
                  className={`chip-xs${draft.kind === 'business' ? ' on' : ''}`}
                  onClick={() => setDraft({ ...draft, kind: 'business' })}
                >
                  {t('cards.kindBusiness', 'Business')}
                </button>
                <button
                  className={`chip-xs${draft.kind === 'person' ? ' on' : ''}`}
                  onClick={() => setDraft({ ...draft, kind: 'person', category: '' })}
                >
                  {t('cards.kindPerson', 'Person')}
                </button>
              </div>
            </div>

            {draft.kind === 'business' && (
              <label className="cards-field">
                <span>{t('cards.category', 'Category')}</span>
                <select
                  value={draft.category}
                  onChange={e => setDraft({ ...draft, category: e.target.value })}
                >
                  <option value="">{t('cards.categoryNone', 'None')}</option>
                  {BUSINESS_CATEGORIES.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
            )}

            <div className="cards-field">
              <span>{t('cards.address', 'Address')}</span>
              <input
                value={addressQuery}
                onChange={e => setAddressQuery(e.target.value)}
                placeholder={t('cards.addressPlaceholder', 'Search for the address')}
              />
              {draft.address && (
                <div className="cards-picked">📍 {draft.address}</div>
              )}
              {addressQuery.trim() && results.length > 0 && (
                <div className="cards-suggest">
                  {results.map(r => (
                    <button key={r.id} className="cards-suggest-item" onClick={() => void pickAddress(r.id)}>
                      <span className="cards-suggest-name">{r.name}</span>
                      <span className="cards-suggest-meta">{r.meta}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="cards-field">
              <span>{t('nearby.radius', 'Radius')}</span>
              <RadiusPicker
                value={draft.radiusKm}
                onChange={(km) => setDraft({ ...draft, radiusKm: km })}
              />
            </div>

            <div className="cards-field">
              <span>
                {t('nearby.categories', 'Categories')}
                {' · '}
                {selectedCount}
              </span>
              <div className="chip-rail">
                <button
                  className={`chip-xs${draft.categories.length === 0 ? ' on' : ''}`}
                  onClick={() => setDraft({ ...draft, categories: [] })}
                >
                  {t('nearby.all', 'All')}
                </button>
                {NEARBY_CATEGORIES.map(cat => {
                  const on = draft.categories.length
                    ? draft.categories.includes(cat.id)
                    : true
                  return (
                    <button
                      key={cat.id}
                      className={`chip-xs${on ? ' on' : ''}`}
                      onClick={() => toggleCategory(cat.id)}
                      title={t(cat.labelKey)}
                    >
                      <span className="chip-dot" style={{ background: cat.color }} />
                      {t(cat.labelKey)}
                    </button>
                  )
                })}
              </div>
            </div>

            <label className="cards-field">
              <span>{t('cards.logo', 'Logo or photo (a link)')}</span>
              <input
                value={draft.logoUrl}
                onChange={e => setDraft({ ...draft, logoUrl: e.target.value })}
                placeholder="https://"
              />
            </label>

            <label className="cards-field">
              <span>{t('cards.accent', 'Accent colour')}</span>
              <input
                type="color"
                value={draft.accent}
                onChange={e => setDraft({ ...draft, accent: e.target.value })}
              />
            </label>

            {error && <div className="cards-error">{error}</div>}

            <div className="cards-modal-acts">
              <button className="cards-btn ghost" onClick={() => setDraft(null)}>
                {t('cards.cancel', 'Cancel')}
              </button>
              <button className="cards-btn" onClick={() => void save()} disabled={busy}>
                {t('cards.save', 'Save')}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
