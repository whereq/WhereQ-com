import { metersBetween } from './distance'

/**
 * A friendship, as `GET /api/friends` returns it.
 *
 * The endpoint lists the **accepted** friendships only — a request that is
 * still pending is not in the list (and there is no endpoint for the
 * incoming requests yet).
 */
export interface Friendship {
  id: number
  user_id: number
  friend_id: number
  status: string
  /** The **other** person's username — the endpoint resolves it for us. */
  friend_username: string | null
}

/** One friend, as the social page renders them. */
export interface FriendRow {
  /** Stable key — the friendship's own id. */
  key: number
  /** The other person's local user id. */
  id: number
  name: string
  initial: string
  /** Their live location, when they are sharing one right now. */
  live: { lat: number; lng: number } | null
  /** How far they are, when we know our own position too. */
  distance: number | null
}

/** A live location, keyed by the user's local id. */
export type Presence = Map<number, { lat: number; lng: number }>

/**
 * Join the roster with the presence channel.
 *
 * The join is on the **local user id**, not the name: the roster carries
 * `users.username`, while the presence payload carries the display name the
 * client sends — two different strings for the same person.
 *
 * A friendship row is stored from either end, so the other person's id is
 * the one that is not ours.
 */
export function buildFriendRows(
  roster: Friendship[],
  myId: number,
  presence: Presence,
  myLocation: { lat: number; lng: number } | null,
): FriendRow[] {
  return roster.map((r) => {
    const otherId = r.user_id === myId ? r.friend_id : r.user_id
    const live = presence.get(otherId) ?? null
    const name = r.friend_username ?? `#${otherId}`
    return {
      key: r.id,
      id: otherId,
      name,
      initial: (name[0] ?? '?').toUpperCase(),
      live,
      distance: live && myLocation ? metersBetween(myLocation, live) : null,
    }
  })
}
