import { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react'
import keycloak from '@/auth/keycloak'

interface UserInfo {
  /** Keycloak subject (stable user id) */
  id: string
  username: string
  email: string
  displayName: string
  avatar: string | undefined
}

/** Resolve a Keycloak avatar/picture claim to a usable URL (or undefined). */
function resolveAvatarUrl(raw: string | undefined): string | undefined {
  if (!raw) return undefined
  if (raw.startsWith('data:') || raw.startsWith('http://') || raw.startsWith('https://')) return raw
  // Relative path from Keycloak — prepend the auth server base URL.
  const base = (keycloak.authServerUrl || '').replace(/\/+$/, '')
  return base ? `${base}${raw.startsWith('/') ? '' : '/'}${raw}` : undefined
}

interface AuthContextValue {
  user: UserInfo | null
  token: string | undefined
  roles: string[]
  isAuthenticated: boolean
  loading: boolean
  login: () => void
  register: () => void
  logout: () => void
}

function readRoles(): string[] {
  const realm = keycloak.tokenParsed?.['realm_access'] as { roles?: string[] } | undefined
  return realm?.roles ?? []
}

function readUser(): UserInfo | null {
  const tp = keycloak.tokenParsed
  if (!keycloak.authenticated || !tp) return null
  const idtp = (keycloak.idTokenParsed ?? {}) as Record<string, unknown>
  const username = (tp['preferred_username'] as string | undefined) ?? ''
  const email = (tp['email'] as string | undefined) ?? ''
  const first = (tp['given_name'] as string | undefined)?.trim() ?? ''
  const last = (tp['family_name'] as string | undefined)?.trim() ?? ''
  const fullName = [first, last].filter(Boolean).join(' ')
  // Accept the avatar from the access token OR the ID token, under either the
  // custom `avatar` claim or the standard OIDC `picture` claim — so it works
  // regardless of which token the Keycloak mapper targets.
  const avatarRaw = (tp['avatar'] ?? tp['picture'] ?? idtp['avatar'] ?? idtp['picture']) as
    string | undefined
  return {
    id: (tp['sub'] as string | undefined) ?? '',
    username,
    email,
    displayName: fullName || username || email,
    avatar: resolveAvatarUrl(avatarRaw),
  }
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(() => readUser())
  const [token, setTokenState] = useState<string | undefined>(keycloak.token)
  const [roles, setRoles] = useState<string[]>(() => readRoles())
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  // Proactively refresh the token every 60 s (refresh when < 30 s remain),
  // syncing derived state on each successful refresh.
  useEffect(() => {
    if (!keycloak.authenticated) return
    refreshTimer.current = setInterval(async () => {
      try {
        const refreshed = await keycloak.updateToken(30)
        if (refreshed) {
          setTokenState(keycloak.token)
          setUser(readUser())
          setRoles(readRoles())
        }
      } catch {
        // Refresh failed — drop to anonymous; next API call redirects to login.
        setUser(null)
        setTokenState(undefined)
        setRoles([])
      }
    }, 60_000)
    return () => {
      if (refreshTimer.current) clearInterval(refreshTimer.current)
    }
  }, [])

  const login = () => keycloak.login()
  const register = () => keycloak.register()
  const logout = () => keycloak.logout({ redirectUri: window.location.origin })

  return (
    <AuthContext.Provider value={{
      user,
      token,
      roles,
      isAuthenticated: !!keycloak.authenticated,
      loading: false,
      login,
      register,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
