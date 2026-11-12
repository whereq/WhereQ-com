import type { LogoVariant } from '@/types/map'

interface LogoProps {
  variant?: LogoVariant
  size?: number
  accent?: string
}

export function Logo({ variant = 'mono', size = 26, accent = 'var(--accent)' }: LogoProps) {
  if (variant === 'globe') {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-label="whereq logo">
        <circle cx="16" cy="16" r="13" stroke={accent} strokeWidth="2.2" />
        <ellipse cx="16" cy="16" rx="13" ry="4.2" stroke={accent} strokeWidth="1.4" opacity="0.65" />
        <ellipse cx="16" cy="16" rx="5.2" ry="13" stroke={accent} strokeWidth="1.4" opacity="0.65" />
        <path d="M19.5 22.5 L 27 30" stroke={accent} strokeWidth="3" strokeLinecap="round" />
        <circle cx="16" cy="16" r="1.8" fill={accent} />
      </svg>
    )
  }
  if (variant === 'pin') {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <path d="M16 4 C 9 4 5 9 5 14 C 5 22 16 28 16 28 C 16 28 27 22 27 14 C 27 9 23 4 16 4 Z" fill={accent} />
        <text x="16" y="19" textAnchor="middle" fontFamily="var(--font-display)" fontSize="13" fontWeight="700" fill="var(--accent-ink)">Q</text>
      </svg>
    )
  }
  if (variant === 'compass') {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="13" stroke={accent} strokeWidth="2" />
        <polygon points="16,5 19,16 16,27 13,16" fill={accent} opacity="0.4" />
        <polygon points="16,5 19,16 16,16" fill={accent} />
        <text x="16" y="14" textAnchor="middle" fontSize="9" fontWeight="700" fontFamily="var(--font-display)" fill={accent}>Q</text>
      </svg>
    )
  }
  // mono (default — locked in per DESIGN_DECISIONS.md)
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <rect x="2" y="2" width="28" height="28" rx="3" fill={accent} />
      <text x="16" y="23" textAnchor="middle" fontSize="20" fontWeight="700" fontFamily="var(--font-display)" fill="var(--accent-ink)">Q</text>
    </svg>
  )
}
