import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '@/lib/api'

interface NeighborhoodDTO {
  id: number
  name: string
  city: string | null
  country: string | null
  walkability_score: number
  transit_score: number
  food_score: number
  schools_score: number
  overall_score: number
}

export function GuidesPage() {
  const { t } = useTranslation()
  const [neighborhoods, setNeighborhoods] = useState<NeighborhoodDTO[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<NeighborhoodDTO[]>('/neighborhoods?limit=50')
      .then(setNeighborhoods)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <main className="content-page">
      <div className="content-page-inner">
        <div className="content-page-hd">
          <h1>{t('pages.guides.title')}</h1>
          <p>{t('pages.guides.subtitle')}</p>
        </div>

        {loading && <div className="content-empty">Loading neighbourhoods...</div>}

        {!loading && neighborhoods.length === 0 && (
          <div className="content-empty">No neighbourhood guides yet.</div>
        )}

        <div className="content-grid">
          {neighborhoods.map(nb => (
            <div key={nb.id} className="content-card">
              <h3>{nb.name}</h3>
              <p>{[nb.city, nb.country].filter(Boolean).join(' · ')}</p>
              <div className="content-score-row">
                <span className="content-score-pill" style={{ color: 'var(--accent)' }}>Walk {nb.walkability_score}</span>
                <span className="content-score-pill" style={{ color: 'var(--info)' }}>Transit {nb.transit_score}</span>
                <span className="content-score-pill" style={{ color: 'var(--success)' }}>Food {nb.food_score}</span>
                <span className="content-score-pill" style={{ color: 'var(--warn)' }}>Schools {nb.schools_score}</span>
              </div>
              <div className="meta">Overall score: {nb.overall_score}</div>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
