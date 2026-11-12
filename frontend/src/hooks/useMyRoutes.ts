import { useCallback, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

export interface MyRoute {
  id: number
  name: string
  total_distance_km: number | null
  duration_minutes: number | null
  created_at: string
}

/** The signed-in user's own routes (empty for anonymous). */
export function useMyRoutes() {
  const [routes, setRoutes] = useState<MyRoute[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!isAuthenticated()) { setRoutes([]); return }
    setLoading(true)
    try {
      setRoutes(await api.get<MyRoute[]>('/routes/mine'))
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  return { routes, loading, refresh }
}
