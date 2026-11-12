import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '@/lib/api'
import type { PlaceDTO } from '@/hooks/usePlaces'

interface StoryDTO {
  id: number
  place_id: number
  title: string
  content: string
  category: string
}

export function MemorialsPage() {
  const { t } = useTranslation()
  const [places, setPlaces] = useState<PlaceDTO[]>([])
  const [stories, setStories] = useState<Record<number, StoryDTO[]>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<PlaceDTO[]>('/places?kind=memorial&limit=50')
      .then(async (memorials) => {
        setPlaces(memorials)
        // Fetch stories for each memorial
        const storyMap: Record<number, StoryDTO[]> = {}
        await Promise.all(
          memorials.map(async (m) => {
            try {
              const s = await api.get<StoryDTO[]>(`/stories?place_id=${m.id}`)
              storyMap[m.id] = s
            } catch { /* ignore */ }
          })
        )
        setStories(storyMap)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <main className="content-page">
      <div className="content-page-inner">
        <div className="content-page-hd">
          <h1>{t('pages.memorials.title')}</h1>
          <p>{t('pages.memorials.subtitle')}</p>
        </div>

        {loading && <div className="content-empty">Loading memorial places...</div>}

        {!loading && places.length === 0 && (
          <div className="content-empty">No memorial places found.</div>
        )}

        <div className="content-grid">
          {places.map(place => {
            const placeStories = stories[place.id] ?? []
            return (
              <div key={place.id} className="content-card">
                <h3>{place.name}</h3>
                <p>{place.description || place.sub || ''}</p>
                {placeStories.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    {placeStories.map(s => (
                      <div key={s.id} style={{ marginTop: 8 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>{s.title}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5, marginTop: 2 }}>
                          {s.content.length > 120 ? s.content.slice(0, 120) + '...' : s.content}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="meta">
                  {[place.city, place.country].filter(Boolean).join(' · ')}
                  {placeStories.length > 0 && ` · ${placeStories.length} story${placeStories.length > 1 ? 'ies' : ''}`}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </main>
  )
}
