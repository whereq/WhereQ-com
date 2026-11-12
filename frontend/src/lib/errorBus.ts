/**
 * The error bus — one place where a failure becomes visible to the user.
 *
 * The app used to swallow every failed request: ~20 call sites had an empty
 * `catch {}`, so a 401 rendered as "No results found" and a failed hazard
 * report gave no feedback at all. `lib/api.ts` now reports every failed
 * request here, and `components/ui/ErrorToaster.tsx` renders them.
 *
 * It is deliberately not a React context: the fetch wrapper is a plain module
 * with no React dependency, and a module-level pub/sub keeps it that way.
 */

export type ErrorLevel = 'error' | 'warning' | 'info'

export interface AppError {
  id: number
  /** An i18n key. When set, the toaster renders the translation, not `message`. */
  code?: string
  /** Interpolation values for the i18n key (e.g. `{ status: 500 }`). */
  vars?: Record<string, string | number>
  /** The raw message — used when there is no i18n key. */
  message: string
  level: ErrorLevel
}

type Listener = (error: AppError) => void

const listeners = new Set<Listener>()
/** key → when it was last reported, so one repeated failure is shown once. */
const seen = new Map<string, number>()
let nextId = 1

/**
 * How long the same message stays quiet. A background layer that polls every
 * 30s and keeps failing would otherwise stack a toast on every tick.
 */
const DEDUPE_MS = 30_000

/** Report a failure to the user. */
export function reportError(
  message: string,
  opts: { code?: string; vars?: Record<string, string | number>; level?: ErrorLevel } = {},
): void {
  const key = opts.code ?? message
  const now = Date.now()
  const last = seen.get(key)
  if (last !== undefined && now - last < DEDUPE_MS) return
  seen.set(key, now)

  // Keep the dedup map from growing without bound.
  for (const [k, ts] of seen) {
    if (now - ts > DEDUPE_MS * 4) seen.delete(k)
  }

  const error: AppError = {
    id: nextId++,
    message,
    level: opts.level ?? 'error',
    ...(opts.code ? { code: opts.code } : {}),
    ...(opts.vars ? { vars: opts.vars } : {}),
  }
  for (const listener of listeners) listener(error)
}

/** Subscribe to reported errors. Returns an unsubscribe function. */
export function subscribeErrors(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
