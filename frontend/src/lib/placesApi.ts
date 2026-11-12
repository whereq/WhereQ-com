import { api } from './api'
import type { PlaceCounts, PlacePin } from '@/types/place'

interface RawPin {
  id: number; name: string; lat: number; lng: number
  kind: string; category: string; sub: string | null
}

interface PlaceDetail {
  id: number
  name?: string
  description?: string | null
  address: string | null
  city: string | null
  metadata_json: Record<string, unknown> | null
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '' && v !== null) sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const placesApi = {
  /** Viewport POI pins for the given kinds (essentials) and/or POI categories. */
  map: async (opts: { bbox: string; kinds?: string[]; categories?: string[]; cuisines?: string[]; limit?: number }) => {
    const raw = await api.get<RawPin[]>('/places/map' + qs({
      bbox: opts.bbox,
      kinds: opts.kinds?.join(','),
      categories: opts.categories?.join(','),
      cuisines: opts.cuisines?.join(','),
      limit: opts.limit,
    }))
    return raw.map((r): PlacePin => ({
      id: r.id, title: r.name, lat: r.lat, lng: r.lng,
      kind: r.kind, category: r.category, sub: r.sub,
    }))
  },

  /** Viewport counts by kind + `cat:<category>`. */
  counts: (bbox: string) => api.get<PlaceCounts>('/places/counts' + qs({ bbox })),

  detail: (id: number) => api.get<PlaceDetail>(`/places/${id}`),
}
