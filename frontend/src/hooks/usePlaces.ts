import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export interface PlaceDTO {
  id: number
  name: string
  description: string | null
  latitude: number
  longitude: number
  address: string | null
  city: string | null
  country: string | null
  category: string
  kind: string
  sub: string | null
  metadata_json: Record<string, unknown> | null
  view_count: number
  created_at: string
}

interface UsePlacesOptions {
  kind?: string
  category?: string
  search?: string
}

export function usePlaces(options: UsePlacesOptions = {}) {
  const [places, setPlaces] = useState<PlaceDTO[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { kind, category, search } = options

  useEffect(() => {
    let cancelled = false

    async function fetchPlaces() {
      setLoading(true)
      setError(null)
      try {
        const params = new URLSearchParams()
        if (kind) params.set('kind', kind)
        if (category) params.set('category', category)
        if (search) params.set('search', search)
        const qs = params.toString()
        const data = await api.get<PlaceDTO[]>(`/places${qs ? `?${qs}` : ''}`)
        if (!cancelled) setPlaces(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load places')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchPlaces()
    return () => { cancelled = true }
  }, [kind, category, search])

  return { places, loading, error, setPlaces }
}
