import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export interface StoryDTO {
  id: number
  place_id: number
  author_id: number
  title: string
  content: string
  category: string
  is_published: boolean
  created_at: string
}

export function useStories(placeId?: number) {
  const [stories, setStories] = useState<StoryDTO[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (placeId == null) {
      setStories([])
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)

    api.get<StoryDTO[]>(`/stories?place_id=${placeId}`)
      .then(data => { if (!cancelled) setStories(data) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load stories') })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [placeId])

  return { stories, loading, error }
}
