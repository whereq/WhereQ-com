import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'solid' | 'outline' | 'ghost' | 'danger' | 'chip'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style. `chip` reuses the shared `.chip` rail look (QUICK CATEGORIES). */
  variant?: ButtonVariant
  size?: ButtonSize
  /** Toggle / pressed state (chip, outline, ghost). */
  selected?: boolean
  /** Leading icon node. */
  icon?: ReactNode
  /** Square, icon-only button (ignores `size` padding). */
  iconOnly?: boolean
  /** Stretch to the container width. */
  block?: boolean
}

/**
 * Generic metroUI button — corner radius `--r-xs` across the app.
 *
 * The `chip` variant deliberately renders the shared `.chip` / `.chip.on`
 * classes so toggle rails (QUICK CATEGORIES, LOCAL ON THE MAP) stay visually
 * identical while sharing one component.
 */
export function Button({
  variant = 'outline',
  size = 'md',
  selected = false,
  icon,
  iconOnly = false,
  block = false,
  className = '',
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes =
    variant === 'chip'
      ? ['chip', selected && 'on', block && 'ui-btn--block', className]
      : [
          'ui-btn',
          `ui-btn--${variant}`,
          iconOnly ? 'ui-btn--icon' : `ui-btn--${size}`,
          selected && 'is-selected',
          block && 'ui-btn--block',
          className,
        ]

  return (
    <button type={type} className={classes.filter(Boolean).join(' ')} {...rest}>
      {icon && <span className="ui-btn-ic">{icon}</span>}
      {children}
    </button>
  )
}
