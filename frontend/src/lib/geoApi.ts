import { api } from './api'
import type { GeoAtResponse, GeoBoundary, GeoConcept, GeoPlace } from '@/types/geo'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '' && v !== null) sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

/** The outlines of a viewport — and whether the answer was truncated. */
export interface GeoBoundaryList {
  /** How many outlines matched the filter. */
  total: number
  /** True when the limit cut the answer short. */
  truncated: boolean
  items: GeoBoundary[]
}

/**
 * The administrative geography feed.
 *
 * Public read-only endpoints — the data is open (ODbL 1.0 / CC-BY 4.0) and
 * the attribution travels on every row. Nothing here spends upstream quota:
 * the rows are already crawled from whereq.cloud into the database.
 */
export const geoApi = {
  /** The vocabulary: every kind of administrative place, with our counts. */
  concepts: () => api.get<GeoConcept[]>('/geo/concepts'),

  /** The administrative places inside a viewport. */
  places: (opts: { bbox?: string; kind?: string[]; source?: string[]; q?: string; hasBoundary?: boolean; limit?: number }) =>
    api.get<GeoPlace[]>('/geo/places' + qs({
      bbox: opts.bbox,
      kind: opts.kind?.join(','),
      source: opts.source?.join(','),
      q: opts.q,
      has_boundary: opts.hasBoundary,
      limit: opts.limit,
    })),

  /** Every outline inside a viewport, in one response. */
  boundaries: (opts: { bbox?: string; kind?: string[]; source?: string[]; simplifyM?: number; limit?: number }) =>
    api.get<GeoBoundaryList>('/geo/boundaries' + qs({
      bbox: opts.bbox,
      kind: opts.kind?.join(','),
      source: opts.source?.join(','),
      simplify_m: opts.simplifyM,
      limit: opts.limit,
    })),

  /** One place's outline. */
  boundary: (uid: string, simplifyM?: number) =>
    api.get<GeoBoundary>(`/geo/places/${encodeURIComponent(uid)}/boundary` + qs({ simplify_m: simplifyM })),

  /** Everything that contains a point — broadest first. */
  at: (lat: number, lng: number) =>
    api.get<GeoAtResponse>('/geo/at' + qs({ lat, lng })),
}
