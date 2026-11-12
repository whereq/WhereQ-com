import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'

interface SavedPlaceDTO {
  id: number
  user_id: number
  place_id: number
  label: string | null
  created_at: string
}

export function useSavedPlaces() {
  const [savedPlaces, setSavedPlaces] = useState<SavedPlaceDTO[]>([])
  const [loading, setLoading] = useState(false)

  const fetch = useCallback(async () => {
    if (!isAuthenticated()) return
    setLoading(true)
    try {
      const data = await api.get<SavedPlaceDTO[]>('/saved-places')
      setSavedPlaces(data)
    } catch {
      // silently fail — user may not be logged in
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const savePlace = useCallback(async (placeId: number, label?: string) => {
    const sp = await api.post<SavedPlaceDTO>('/saved-places', { place_id: placeId, label })
    setSavedPlaces(prev => [sp, ...prev])
    return sp
  }, [])

  const unsavePlace = useCallback(async (placeId: number) => {
    await api.delete(`/saved-places/${placeId}`)
    setSavedPlaces(prev => prev.filter(s => s.place_id !== placeId))
  }, [])

  const isSaved = useCallback(
    (placeId: number) => savedPlaces.some(s => s.place_id === placeId),
    [savedPlaces],
  )

  return { savedPlaces, loading, savePlace, unsavePlace, isSaved, refresh: fetch }
}
