import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { subscribeErrors, type AppError } from '@/lib/errorBus'

/** How many toasts are visible at once. */
const MAX_VISIBLE = 3
/** How long a toast stays on screen. */
const DISMISS_MS = 6000

/**
 * Renders the errors reported on the error bus.
 *
 * Mounted once, next to the router, so every failed request in the app has a
 * visible outcome. Messages are translated when the report carries an i18n
 * `code`; otherwise the raw message is shown.
 */
export function ErrorToaster() {
  const { t } = useTranslation()
  const [errors, setErrors] = useState<AppError[]>([])

  useEffect(() => {
    return subscribeErrors((error) => {
      setErrors(prev => [...prev, error].slice(-MAX_VISIBLE))
      window.setTimeout(() => {
        setErrors(prev => prev.filter(e => e.id !== error.id))
      }, DISMISS_MS)
    })
  }, [])

  const dismiss = (id: number) => {
    setErrors(prev => prev.filter(e => e.id !== id))
  }

  if (errors.length === 0) return null

  return (
    <div className="wq-toasts" role="status" aria-live="polite">
      {errors.map(error => (
        <div key={error.id} className={`wq-toast wq-toast--${error.level}`}>
          <span className="wq-toast__msg">
            {error.code ? t(error.code, error.vars ?? {}) : error.message}
          </span>
          <button
            type="button"
            className="wq-toast__x"
            onClick={() => dismiss(error.id)}
            aria-label={t('toast.dismiss')}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
