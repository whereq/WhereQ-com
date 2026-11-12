import { api } from './api'
import type { PlaceCardDTO, PlaceCardInput } from '@/types/placeCard'

/**
 * The user's own cards.
 *
 * The list is always the caller's — there is no id in the path for it — and a
 * card that is not yours answers 404, because a card is private until it is
 * published.
 */
export const placeCardsApi = {
  list: () => api.get<PlaceCardDTO[]>('/place-cards'),

  get: (id: number) => api.get<PlaceCardDTO>(`/place-cards/${id}`),

  create: (body: PlaceCardInput) => api.post<PlaceCardDTO>('/place-cards', body),

  update: (id: number, body: Partial<PlaceCardInput>) =>
    api.patch<PlaceCardDTO>(`/place-cards/${id}`, body),

  remove: (id: number) => api.delete(`/place-cards/${id}`),
}
