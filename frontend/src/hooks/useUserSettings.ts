import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { nearbyApi } from '@/lib/nearbyApi'
import { DEFAULT_RADIUS_KM } from '@/lib/nearbyCategories'

export interface UserSettings {
  /** The nearby radius, in kilometres. */
  radiusKm: number
  /**
   * The categories the user kept. An **empty list means every category** —
   * the same convention the API and the database use.
   */
  categories: string[]
}

export const DEFAULT_SETTINGS: UserSettings = {
  radiusKm: DEFAULT_RADIUS_KM,
  categories: [],
}

const STORAGE_KEY = 'whereq:user-settings'

function readLocal(): UserSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw) as Partial<UserSettings>
    return {
      radiusKm:
        typeof parsed.radiusKm === 'number' && parsed.radiusKm > 0
          ? parsed.radiusKm
          : DEFAULT_SETTINGS.radiusKm,
      categories: Array.isArray(parsed.categories)
        ? parsed.categories.filter(c => typeof c === 'string')
        : [],
    }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

function writeLocal(settings: UserSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    /* ignore — the settings simply stay on the server */
  }
}

/**
 * The user's own settings: the nearby radius and the category selection.
 *
 * A signed-in user gets them from the account, so the choice follows them
 * across devices; a signed-out visitor gets the same defaults kept in the
 * browser. A change made while signed out is pushed to the account when they
 * sign in, so it is not silently lost.
 */
export function useUserSettings() {
  const { isAuthenticated } = useAuth()
  const [settings, setSettings] = useState<UserSettings>(DEFAULT_SETTINGS)
  const [loading, setLoading] = useState(true)
  // The live value, so `update` never works from a stale closure.
  const current = useRef<UserSettings>(DEFAULT_SETTINGS)
  // Set when the user changes something while signed out.
  const pendingLocal = useRef(false)

  useEffect(() => {
    let cancelled = false

    if (!isAuthenticated) {
      const local = readLocal()
      current.current = local
      setSettings(local)
      setLoading(false)
      return
    }

    setLoading(true)
    nearbyApi
      .settings()
      .then(saved => {
        if (cancelled) return
        if (pendingLocal.current) {
          // The user changed something while signed out — that choice wins and
          // is written to the account now.
          pendingLocal.current = false
          void nearbyApi
            .saveSettings({
              radius_km: current.current.radiusKm,
              categories: current.current.categories,
            })
            .catch(() => { /* the local value stands */ })
          return
        }
        const next: UserSettings = {
          radiusKm: saved.radius_km ?? DEFAULT_SETTINGS.radiusKm,
          categories: saved.categories ?? [],
        }
        current.current = next
        setSettings(next)
        writeLocal(next)
      })
      .catch(() => {
        // The settings endpoint needs a session; if it fails, keep the local
        // copy rather than resetting the user's choice.
        if (cancelled) return
        const local = readLocal()
        current.current = local
        setSettings(local)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [isAuthenticated])

  const update = useCallback(
    (patch: Partial<UserSettings>) => {
      const next = { ...current.current, ...patch }
      current.current = next
      setSettings(next)
      writeLocal(next)
      if (isAuthenticated) {
        void nearbyApi
          .saveSettings({ radius_km: next.radiusKm, categories: next.categories })
          .catch(() => { /* keep the local value */ })
      } else {
        pendingLocal.current = true
      }
    },
    [isAuthenticated],
  )

  return { settings, update, loading }
}
