import { api } from './api'
import type { Friendship } from './friends'

/** The signed-in user's own profile, in our own `users` table. */
export interface Me {
  id: number
  username: string
  email: string
  is_active: boolean
  locale: string
  theme: string
  created_at: string
}

export const friendsApi = {
  /** The signed-in user's accepted friends. */
  list: () => api.get<Friendship[]>('/friends'),
  /**
   * Our own row in the `users` table.
   *
   * We need the **local** id, not the Keycloak subject: the friendships and
   * the presence channel are both keyed on the local integer id, and the
   * username in the presence payload is the display name the client sends,
   * which is not the same string as `users.username`.
   */
  me: () => api.get<Me>('/auth/me'),
}
