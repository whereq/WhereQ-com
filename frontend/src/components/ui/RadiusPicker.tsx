import { useTranslation } from 'react-i18next'
import { NEARBY_RADII_KM, formatRadius } from '@/lib/nearbyCategories'

/**
 * The **radius** GUI role.
 *
 * "How far?" is the same question everywhere in the whereq universe — the
 * nearby list, a place card's own radius, a user's saved settings — so it is
 * asked the same way everywhere too: a single-choice row of small chips
 * (`.chip-rail` > `.chip-xs`).
 *
 * This component is the **one** definition of that role. It is deliberately
 * presentational: the radius is the caller's business (the account's own
 * settings, or a card's own radius — which is part of the card, not of the
 * account), so the value and the change come in as props.
 *
 * The canonical choices live in `lib/nearbyCategories.ts` — the *radii*, not
 * the markup. Another application adopts the role by copying this component
 * and the two CSS classes; it does not re-invent a radius picker, because a
 * radius picker that looks different in two apps is two controls, not one.
 *
 * @see docs/ARCHITECTURE.md
 */
export function RadiusPicker({
  value,
  onChange,
  label,
  radii = NEARBY_RADII_KM,
}: {
  /** The selected radius, in kilometres. */
  value: number
  /** Called with the chosen radius, in kilometres. */
  onChange: (km: number) => void
  /** The accessible name of the group. Defaults to the app's own word for it. */
  label?: string
  /** The choices. The canonical radii unless a caller has a reason. */
  radii?: number[]
}) {
  const { t } = useTranslation()
  const name = label ?? t('nearby.radius', 'Radius')
  return (
    <div className="chip-rail" role="radiogroup" aria-label={name}>
      {radii.map(km => (
        <button
          key={km}
          type="button"
          role="radio"
          aria-checked={value === km}
          className={`chip-xs${value === km ? ' on' : ''}`}
          onClick={() => onChange(km)}
        >
          {formatRadius(km)}
        </button>
      ))}
    </div>
  )
}
