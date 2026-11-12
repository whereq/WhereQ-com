import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export interface NeighborhoodDTO {
  id: number
  name: string
  description: string | null
  city: string
  country: string
  latitude: number | null
  longitude: number | null
  safety_score: number | null
  walkability_score: number | null
  transit_score: number | null
  food_score: number | null
  schools_score: number | null
  overall_score: number | null
  created_at: string
}

export function useNeighborhood(city?: string) {
  const [neighborhood, setNeighborhood] = useState<NeighborhoodDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function fetchNeighborhood() {
      setLoading(true)
      setError(null)
      try {
        const params = new URLSearchParams({ limit: '1' })
        if (city) params.set('city', city)
        const data = await api.get<NeighborhoodDTO[]>(`/neighborhoods?${params}`)
        if (!cancelled) setNeighborhood(data[0] ?? null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load neighborhood')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchNeighborhood()
    return () => { cancelled = true }
  }, [city])

  return { neighborhood, loading, error }
}
