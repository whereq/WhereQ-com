import { createContext, useContext, useState, ReactNode } from 'react'
import { useFriendsNearby, type FriendLocation } from '@/hooks/useFriendsNearby'

interface FriendsContextValue {
  friends: FriendLocation[]
  connected: boolean
  connect: () => void
  disconnect: () => void
  sendLocation: (lat: number, lng: number, username: string) => void
  /** Our own last known location (set by the map), used for friend distances. */
  myLocation: { lat: number; lng: number } | null
  setMyLocation: (p: { lat: number; lng: number } | null) => void
}

const FriendsContext = createContext<FriendsContextValue | null>(null)

/** One presence WebSocket shared by the map (markers) and the sidebar (list). */
export function FriendsProvider({ children }: { children: ReactNode }) {
  const net = useFriendsNearby()
  const [myLocation, setMyLocation] = useState<{ lat: number; lng: number } | null>(null)
  return (
    <FriendsContext.Provider value={{ ...net, myLocation, setMyLocation }}>
      {children}
    </FriendsContext.Provider>
  )
}

export function useFriendsContext() {
  const ctx = useContext(FriendsContext)
  if (!ctx) throw new Error('useFriendsContext must be used within FriendsProvider')
  return ctx
}
