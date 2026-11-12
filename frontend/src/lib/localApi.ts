import { api } from './api'
import type {
  LocalContentDetail, LocalPin, LocalSearchResponse, LocalTaxonomy,
} from '@/types/local'

function qs(params: Record<string, string | number | string[] | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    sp.set(k, Array.isArray(v) ? v.join(',') : String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export interface LocalMapQuery {
  bbox?: string
  types?: string[]
  categories?: string[]
  sources?: string[]
  from?: string
  to?: string
  q?: string
  limit?: number
}

export const localApi = {
  map: (o: LocalMapQuery) =>
    api.get<LocalPin[]>('/local/map' + qs({
      bbox: o.bbox, types: o.types, categories: o.categories, sources: o.sources,
      from: o.from, to: o.to, q: o.q, limit: o.limit,
    })),
  detail: (id: number) => api.get<LocalContentDetail>(`/local/${id}`),
  taxonomy: () => api.get<LocalTaxonomy>('/local/taxonomy'),
  search: (o: { q: string; types?: string[]; categories?: string[]; sources?: string[]
                from?: string; to?: string; limit?: number; offset?: number }) =>
    api.get<LocalSearchResponse>('/local/search' + qs({
      q: o.q, types: o.types, categories: o.categories, sources: o.sources,
      from: o.from, to: o.to, limit: o.limit, offset: o.offset,
    })),
}
