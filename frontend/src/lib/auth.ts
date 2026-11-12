// Token access is delegated to Keycloak. These helpers keep the previous
// `getToken()` surface so the rest of the app (api client, websockets) does
// not need to know about keycloak-js directly.
import keycloak from '@/auth/keycloak'

export function getToken(): string | null {
  return keycloak.token ?? null
}

export function isAuthenticated(): boolean {
  return !!keycloak.authenticated
}

/**
 * Ensure the access token is valid for at least the next 30 s, refreshing it
 * if necessary. No-op for anonymous sessions. Throws if the refresh fails so
 * callers can fall back to a login redirect.
 */
export async function ensureFreshToken(): Promise<void> {
  if (!keycloak.authenticated) return
  await keycloak.updateToken(30)
}
