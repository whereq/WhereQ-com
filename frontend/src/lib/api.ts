import keycloak from '@/auth/keycloak'
import { ensureFreshToken, getToken } from './auth'
import { reportError } from './errorBus'

const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  // If we have a session, keep the access token fresh and attach it. The site
  // supports anonymous browsing, so a refresh failure (expired/stale session)
  // must NOT force a login redirect — drop to anonymous and continue, so public
  // endpoints still load. Components gate protected features behind sign-in.
  if (keycloak.authenticated) {
    try {
      await ensureFreshToken()
    } catch {
      try {
        keycloak.clearToken()
      } catch {
        /* ignore — proceed anonymously */
      }
    }
  }

  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    })
  } catch {
    // The request never reached the API (offline, DNS, CORS). Every caller
    // swallows this, so it would otherwise look like "no results".
    reportError('network', { code: 'toast.network' })
    throw new ApiError(0, 'Network error')
  }

  if (!res.ok) {
    // A 401 on a request we authenticated means the token was rejected — clear
    // the stale session so later loads are clean. We do NOT auto-redirect to
    // login: the caller decides (e.g. show a "sign in" prompt for gated data).
    if (res.status === 401 && keycloak.authenticated) {
      try {
        keycloak.clearToken()
      } catch {
        /* ignore */
      }
    }
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof body.detail === 'string' ? body.detail : res.statusText
    // This is the single choke point every request goes through, so it is the
    // right place to make a failure visible. A 401 belongs to the sign-in
    // prompt (the caller knows the context), and a 404 usually means an
    // optional resource is simply absent.
    if (res.status !== 401 && res.status !== 404) {
      reportError(detail, { code: 'toast.requestFailed', vars: { status: res.status } })
    }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: 'DELETE' }),
}

export { ApiError }
