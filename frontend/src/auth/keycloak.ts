import Keycloak from 'keycloak-js'

/**
 * Authentication is delegated to an external OpenID Connect provider
 * (Keycloak, or anything OIDC-compatible). The backend only *verifies* the
 * access token; it never issues a session of its own.
 *
 * Authentication is OPTIONAL. When `VITE_KEYCLOAK_URL` is not set — the
 * default for a fresh clone — the SPA runs in anonymous mode: the public
 * browsing endpoints work and sign-in stays hidden. That means a contributor
 * can clone, build and run the app without standing up an identity provider
 * first.
 *
 * To enable sign-in, point `VITE_KEYCLOAK_URL` / `VITE_KEYCLOAK_REALM` /
 * `VITE_KEYCLOAK_CLIENT_ID` at your own realm. See docs/SETUP.md.
 */
const url = (import.meta.env.VITE_KEYCLOAK_URL as string | undefined)?.trim() ?? ''

/**
 * The subset of the keycloak-js surface this app uses. Implemented as a
 * no-op so the rest of the code can treat `keycloak` as a single object
 * regardless of whether a realm is configured.
 */
type AuthClient = Pick<
  Keycloak,
  | 'token'
  | 'authenticated'
  | 'authServerUrl'
  | 'tokenParsed'
  | 'idTokenParsed'
  | 'init'
  | 'login'
  | 'register'
  | 'logout'
  | 'updateToken'
  | 'clearToken'
>

const anonymousClient: AuthClient = {
  token: undefined,
  authenticated: false,
  authServerUrl: undefined,
  tokenParsed: undefined,
  idTokenParsed: undefined,
  init: () => Promise.resolve(true),
  login: () => Promise.resolve(),
  register: () => Promise.resolve(),
  logout: () => Promise.resolve(),
  updateToken: () => Promise.resolve(false),
  clearToken: () => undefined,
}

const keycloak: AuthClient = url
  ? new Keycloak({
      url,
      realm: import.meta.env.VITE_KEYCLOAK_REALM as string,
      clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID as string,
    })
  : anonymousClient

export default keycloak
