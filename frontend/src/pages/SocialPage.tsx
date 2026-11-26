import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/contexts/AuthContext'
import { useFriendsContext } from '@/contexts/FriendsContext'
import { fmtDist } from '@/lib/distance'
import { buildFriendRows, type FriendRow, type Friendship } from '@/lib/friends'
import { friendsApi } from '@/lib/friendsApi'

/**
 * What the page has to show.
 *
 * Five states, each one honest — the page never shows an empty list because
 * a request failed, and it never shows invented people.
 */
export type SocialState =
  /** Signed out: the friends list is tied to the account. */
  | { kind: 'signed-out' }
  /** The roster is still being fetched. */
  | { kind: 'loading' }
  /** The request failed; the toast already said so, the page says it too. */
  | { kind: 'error' }
  /** Signed in, and there are no friends yet. */
  | { kind: 'empty' }
  /** The roster. */
  | { kind: 'ready'; rows: FriendRow[] }

/**
 * The social page: **your friends**, from the API.
 *
 * It used to render six invented people — "Mira Patel — Online · Pier
 * Coffee" and friends, with San Francisco place names — that were never
 * connected to anything. The names looked real, which is the problem: a
 * visitor could not tell them from data.
 *
 * Two sources, joined on the **local** user id:
 *
 * - `GET /api/friends` — the roster: the friendships that are **accepted**.
 * - the presence channel (`FriendsContext`) — who is online and sharing a
 *   location right now.
 *
 * The usernames do not join: the roster carries `users.username`, while the
 * presence payload carries the display name the client sends, so the two are
 * matched on the id, and the id comes from `GET /api/auth/me`.
 */
export function SocialPage() {
  const { isAuthenticated, login } = useAuth()
  const { friends, myLocation } = useFriendsContext()

  /** The roster, or null while it is still loading. */
  const [roster, setRoster] = useState<Friendship[] | null>(null)
  /** Our own local user id — the join key. */
  const [myId, setMyId] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)
  const [reload, setReload] = useState(0)

  const retry = useCallback(() => setReload((n) => n + 1), [])

  useEffect(() => {
    if (!isAuthenticated) {
      setRoster(null)
      setMyId(null)
      setFailed(false)
      return
    }
    let cancelled = false
    setRoster(null)
    setFailed(false)
    ;(async () => {
      try {
        const me = await friendsApi.me()
        const list = await friendsApi.list()
        if (cancelled) return
        setMyId(me.id)
        setRoster(list)
      } catch {
        // The fetch wrapper has already raised the toast; the page says what
        // happened and offers a retry rather than pretending the list is empty.
        if (!cancelled) {
          setRoster([])
          setFailed(true)
        }
      }
    })()
    return () => { cancelled = true }
  }, [isAuthenticated, reload])

  /** Who is online right now, keyed by their local user id. */
  const presence = useMemo(() => {
    const m = new Map<number, { lat: number; lng: number }>()
    for (const f of friends) m.set(f.user_id, { lat: f.lat, lng: f.lng })
    return m
  }, [friends])

  const rows: FriendRow[] = useMemo(
    () =>
      roster && myId !== null
        ? buildFriendRows(roster, myId, presence, myLocation)
        : [],
    [roster, myId, presence, myLocation],
  )

  const state: SocialState = !isAuthenticated
    ? { kind: 'signed-out' }
    : failed
      ? { kind: 'error' }
      : roster === null
        ? { kind: 'loading' }
        : rows.length === 0
          ? { kind: 'empty' }
          : { kind: 'ready', rows }

  return <SocialView state={state} onSignIn={() => login()} onRetry={retry} />
}

/**
 * The page's body — a pure function of the state.
 *
 * Kept separate from the fetching so every state can be rendered and checked
 * on its own; the data lives in the component above, the presentation here.
 */
export function SocialView({
  state,
  onSignIn,
  onRetry,
}: {
  state: SocialState
  onSignIn: () => void
  onRetry: () => void
}) {
  const { t } = useTranslation()

  const head = (
    <div className="content-page-hd">
      <h1>{t('pages.social.title')}</h1>
      <p>{t('pages.social.subtitle')}</p>
    </div>
  )

  // ── Signed out: the page is a locked card, like the search box ──────
  if (state.kind === 'signed-out') {
    return (
      <main className="content-page">
        <div className="content-page-inner">
          {head}
          <div className="content-grid">
            <button className="content-card friend-card" onClick={onSignIn}>
              <span className="av">?</span>
              <div className="info">
                <div className="name">
                  {t('pages.social.locked', 'Sign in to see your friends')}
                </div>
                <div className="status">
                  {t(
                    'pages.social.lockedHint',
                    'Your friends and their live location are tied to your account.',
                  )}
                </div>
              </div>
            </button>
          </div>
        </div>
      </main>
    )
  }

  // ── Loading ──────────────────────────────────────────────────────────
  if (state.kind === 'loading') {
    return (
      <main className="content-page">
        <div className="content-page-inner">
          {head}
          <div className="content-empty">
            {t('pages.social.loading', 'Loading your friends…')}
          </div>
        </div>
      </main>
    )
  }

  // ── Failed: say so, and offer a retry ────────────────────────────────
  if (state.kind === 'error') {
    return (
      <main className="content-page">
        <div className="content-page-inner">
          {head}
          <div className="content-empty">
            <div>{t('pages.social.error', 'Could not load your friends.')}</div>
            <button className="signin-note" onClick={onRetry}>
              {t('pages.social.retry', 'Try again')}
            </button>
          </div>
        </div>
      </main>
    )
  }

  // ── No friends yet ───────────────────────────────────────────────────
  if (state.kind === 'empty') {
    return (
      <main className="content-page">
        <div className="content-page-inner">
          {head}
          <div className="content-empty">
            <div>{t('pages.social.empty', 'You have no friends yet.')}</div>
            <div>
              {t(
                'pages.social.emptyHint',
                'A friend appears here once they accept your request.',
              )}
            </div>
          </div>
        </div>
      </main>
    )
  }

  // ── The roster ───────────────────────────────────────────────────────
  return (
    <main className="content-page">
      <div className="content-page-inner">
        {head}
        <div className="content-grid">
          {state.rows.map((f) => (
            <div key={f.key} className="content-card friend-card">
              <span className="av">{f.initial}</span>
              <div className="info">
                <div className="name">{f.name}</div>
                <div className="status">
                  {f.live
                    ? `${t('friends.sharing', 'Sharing location')}${
                        f.distance !== null ? ` · ${fmtDist(f.distance)}` : ''
                      }`
                    : t('pages.social.offline', 'Offline')}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
