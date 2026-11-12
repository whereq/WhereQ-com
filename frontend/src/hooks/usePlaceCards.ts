import { useEffect, useState, useCallback } from 'react'
import { placeCardsApi } from '@/lib/placeCardsApi'
import { isAuthenticated } from '@/lib/auth'
import type { PlaceCardDTO, PlaceCardInput } from '@/types/placeCard'

/**
 * The caller's own cards.
 *
 * The list is the account's — the API has no id in the path for it — so this
 * hook only ever holds the caller's cards.
 */
export function usePlaceCards() {
  const [cards, setCards] = useState<PlaceCardDTO[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!isAuthenticated()) {
      setCards([])
      return
    }
    setLoading(true)
    try {
      setCards(await placeCardsApi.list())
    } catch {
      // The shared fetch wrapper already reported the failure; the list stays
      // as it was rather than pretending the account owns nothing.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const createCard = useCallback(async (input: PlaceCardInput) => {
    const card = await placeCardsApi.create(input)
    setCards(prev => [card, ...prev])
    return card
  }, [])

  const updateCard = useCallback(async (id: number, input: Partial<PlaceCardInput>) => {
    const card = await placeCardsApi.update(id, input)
    setCards(prev => prev.map(c => (c.id === id ? card : c)))
    return card
  }, [])

  const deleteCard = useCallback(async (id: number) => {
    await placeCardsApi.remove(id)
    setCards(prev => prev.filter(c => c.id !== id))
  }, [])

  return { cards, loading, createCard, updateCard, deleteCard, refresh }
}
