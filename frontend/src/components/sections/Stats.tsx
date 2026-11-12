import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface StatItemProps {
  target: number
  suffix: string
  label: string
  delay: number
}

function StatItem({ target, suffix, label, delay }: StatItemProps) {
  const [display, setDisplay] = useState('0' + suffix)
  const ref = useRef<HTMLSpanElement>(null)
  const started = useRef(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && !started.current) {
        started.current = true
        observer.disconnect()
        setTimeout(() => {
          const duration = 2000
          const start = performance.now()
          const tick = (now: number) => {
            const t = Math.min((now - start) / duration, 1)
            const ease = 1 - Math.pow(1 - t, 4)
            const value = Math.round(ease * target)
            if (target >= 1_000_000) {
              setDisplay((value / 1_000_000).toFixed(1) + 'M' + suffix)
            } else if (target >= 1_000) {
              setDisplay(Math.round(value / 1_000) + 'K' + suffix)
            } else {
              setDisplay(value + suffix)
            }
            if (t < 1) requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
        }, delay)
      }
    }, { threshold: 0.3 })

    observer.observe(el)
    return () => observer.disconnect()
  }, [target, suffix, delay])

  return (
    <div className="stat-item" data-animate data-delay={String(delay)}>
      <span className="stat-number" ref={ref}>{display}</span>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export function Stats() {
  const { t } = useTranslation()

  const stats = [
    { target: 2_000_000, suffix: '+', label: t('stats.places'), delay: 100 },
    { target: 500_000,   suffix: '+', label: t('stats.users'),   delay: 200 },
    { target: 150,       suffix: '+', label: t('stats.countries'),delay: 300 },
    { target: 1_200_000, suffix: '+', label: t('stats.stories'), delay: 400 },
  ]

  return (
    <section className="stats-section" id="stats">
      <div className="container">

        <div className="stats-header" data-animate>
          <div className="section-tag">{t('stats.tag')}</div>
          <h2>{t('stats.title')}</h2>
        </div>

        <div className="stats-grid">
          {stats.map(stat => (
            <StatItem key={stat.label} {...stat} />
          ))}
        </div>

      </div>
    </section>
  )
}
