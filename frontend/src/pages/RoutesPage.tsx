import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/contexts/AuthContext'
import { api } from '@/lib/api'

interface RouteDTO {
  id: number
  user_id: number
  name: string
  description: string | null
  /** The backend sends `total_distance_km` / `duration_minutes` (RouteRead). */
  total_distance_km: number | null
  duration_minutes: number | null
  is_public: boolean
  created_at: string
}

export function RoutesPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [publicRoutes, setPublicRoutes] = useState<RouteDTO[]>([])
  const [myRoutes, setMyRoutes] = useState<RouteDTO[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const fetches: Promise<void>[] = [
      api.get<RouteDTO[]>('/routes?limit=20')
        .then(setPublicRoutes)
        .catch(() => setFailed(true)),
    ]

    if (user) {
      fetches.push(
        api.get<RouteDTO[]>(`/routes/user/${user.id}`)
          .then(setMyRoutes)
          .catch(() => setFailed(true))
      )
    }

    Promise.all(fetches).finally(() => setLoading(false))
  }, [user])

  const formatDate = (iso: string) => new Date(iso).toLocaleDateString()

  return (
    <main className="content-page">
      <div className="content-page-inner">
        <div className="content-page-hd">
          <h1>{t('pages.routes.title')}</h1>
          <p>{t('pages.routes.subtitle')}</p>
        </div>

        {loading && <div className="content-empty">Loading routes...</div>}

        {user && myRoutes.length > 0 && (
          <>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', marginBottom: 12, fontFamily: 'var(--font-display)' }}>
              My Routes
            </h2>
            <div className="content-grid" style={{ marginBottom: 32 }}>
              {myRoutes.map(r => (
                <div key={r.id} className="content-card">
                  <h3>{r.name}</h3>
                  {r.description && <p>{r.description}</p>}
                  <div className="meta">
                    {r.total_distance_km != null && `${r.total_distance_km} km`}
                    {r.duration_minutes != null && ` · ${r.duration_minutes} min`}
                    {` · ${formatDate(r.created_at)}`}
                    {r.is_public && ' · Public'}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {publicRoutes.length > 0 && (
          <>
            <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text)', marginBottom: 12, fontFamily: 'var(--font-display)' }}>
              Public Routes
            </h2>
            <div className="content-grid">
              {publicRoutes.map(r => (
                <div key={r.id} className="content-card">
                  <h3>{r.name}</h3>
                  {r.description && <p>{r.description}</p>}
                  <div className="meta">
                    {r.total_distance_km != null && `${r.total_distance_km} km`}
                    {r.duration_minutes != null && ` · ${r.duration_minutes} min`}
                    {` · ${formatDate(r.created_at)}`}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {failed && (
          <div className="content-empty">{t('pages.routes.error')}</div>
        )}

        {!loading && !failed && publicRoutes.length === 0 && myRoutes.length === 0 && (
          <div className="content-empty">No routes found.</div>
        )}
      </div>
    </main>
  )
}
