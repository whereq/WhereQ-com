import { api } from '@/lib/api'
import type {
  CatchmentHit, MapPin, PaginatedSchools, SchoolDetail, SchoolFilters, Taxonomy,
} from './types'

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

function filterParams(f: Partial<SchoolFilters>) {
  return {
    country: f.country, province: f.province, region: f.region, board: f.board,
    type: f.type, board_type: f.board_type, program: f.program,
  }
}

export const schoolsApi = {
  taxonomy: () => api.get<Taxonomy>('/schools/taxonomy'),

  list: (opts: {
    filters: Partial<SchoolFilters>
    q?: string
    sort?: string
    order?: 'asc' | 'desc'
    page?: number
    page_size?: number
    bbox?: string
    rank?: boolean
  }) =>
    api.get<PaginatedSchools>(
      '/schools' + qs({
        ...filterParams(opts.filters), q: opts.q, sort: opts.sort, order: opts.order,
        page: opts.page, page_size: opts.page_size, bbox: opts.bbox, rank: opts.rank,
      }),
    ),

  mapPins: (opts: { filters: Partial<SchoolFilters>; q?: string; bbox?: string; limit?: number }) =>
    api.get<MapPin[]>(
      '/schools/map' + qs({ ...filterParams(opts.filters), q: opts.q, bbox: opts.bbox, limit: opts.limit }),
    ),

  detail: (id: number) => api.get<SchoolDetail>(`/schools/${id}`),

  at: (lat: number, lng: number) => api.get<CatchmentHit[]>(`/schools/at${qs({ lat, lng })}`),
}
