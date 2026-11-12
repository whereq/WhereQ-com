import { api } from './api'
import type { NearbyResponse, UserSettingsDTO } from '@/types/nearby'

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '' && v !== null) sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const nearbyApi = {
  /**
   * Everything near the centre — the POIs, the fuel stations, the news and
   * the schools within the radius, merged into one list.
   *
   * An empty `categories` list means "every category" (the server treats a
   * missing filter the same way).
   */
  list: (opts: {
    lat: number
    lng: number
    radiusKm: number
    categories?: string[]
    limit?: number
  }) =>
    api.get<NearbyResponse>('/nearby' + qs({
      lat: opts.lat,
      lng: opts.lng,
      radius_km: opts.radiusKm,
      categories: opts.categories?.join(','),
      limit: opts.limit,
    })),

  /** The category vocabulary the filter chips use. */
  categories: () => api.get<{ categories: string[] }>('/nearby/categories'),

  /** The caller's own settings — needs a session. */
  settings: () => api.get<UserSettingsDTO>('/user-settings'),

  /** Update the caller's own settings — needs a session. */
  saveSettings: (patch: { radius_km?: number; categories?: string[] }) =>
    api.patch<UserSettingsDTO>('/user-settings', patch),
}
