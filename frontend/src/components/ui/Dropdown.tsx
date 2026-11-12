import { useEffect, useRef, useState, type ReactNode } from 'react'

export interface DropdownProps {
  /** Content rendered inside the trigger button. */
  trigger: ReactNode
  /** Menu body. Receives a `close()` callback when given as a function. */
  children: ReactNode | ((close: () => void) => ReactNode)
  /** Which edge the menu aligns to. */
  align?: 'left' | 'right'
  /** Accessible label for the trigger button. */
  label?: string
  className?: string
  triggerClassName?: string
  menuClassName?: string
}

/**
 * Generic metroUI dropdown: a trigger button + an absolutely-positioned menu
 * that closes on outside-click or Escape. Pair the menu body with `Button`
 * (variant="ghost", block) or the `.ui-dd-item` helper class for menu rows.
 */
export function Dropdown({
  trigger,
  children,
  align = 'left',
  label,
  className = '',
  triggerClassName = '',
  menuClassName = '',
}: DropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const close = () => setOpen(false)

  return (
    <div className={`ui-dd ${className}`.trim()} ref={ref}>
      <button
        type="button"
        className={`ui-dd-trigger ${triggerClassName}`.trim()}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((o) => !o)}
      >
        {trigger}
      </button>
      {open && (
        <div className={`ui-dd-menu ui-dd-menu--${align} ${menuClassName}`.trim()} role="menu">
          {typeof children === 'function' ? children(close) : children}
        </div>
      )}
    </div>
  )
}
