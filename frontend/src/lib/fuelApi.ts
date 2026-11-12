import { api } from './api'

/** One aggregated fuel price series (state / national / metro average). */
export interface FuelSeries {
  id: number
  region: string | null
  geo: string | null
  item: string
  /** Normalised product: regular | midgrade | premium | diesel | heating. */
  product: string | null
  /** Unit as published by the source ("Cents per litre", "$/GAL"). */
  unit: string | null
  /** Currency of the normalised value (CAD / USD / MXN). */
  currency: string | null
  /** The value converted to local currency per litre — the same unit the
   *  station prices use, so an average and a station price are comparable. */
  value_per_litre: number | null
  frequency: string | null
  latest_period: string | null
  latest_value: number | null
  prev_value: number | null
}

/** Query-string values may be numbers (lat, lng, radius, limit) or strings. */
function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

/** One gas station with its latest prices. */
export interface FuelStation {
  id: number
  name: string
  brand: string | null
  city: string | null
  country: string | null
  lat: number
  lng: number
  prices: Record<string, { price?: number; observed_at?: string }>
  currency: string | null
  unit: string | null
  observed_at: string | null
  product: string | null
  price: number | null
  distance_km: number | null
}

export const fuelApi = {
  /** Gas stations with their prices — nearest or cheapest first. */
  stations: (opts: {
    q?: string
    lat?: number
    lng?: number
    radiusKm?: number
    bbox?: string
    product?: string
    sort?: 'distance' | 'price'
    limit?: number
  }) => api.get<FuelStation[]>('/fuel/stations' + qs({
    q: opts.q,
    lat: opts.lat,
    lng: opts.lng,
    radius_km: opts.radiusKm,
    bbox: opts.bbox,
    product: opts.product,
    sort: opts.sort,
    limit: opts.limit,
  })),
}
