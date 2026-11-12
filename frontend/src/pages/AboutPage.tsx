import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useScrollAnimate } from '@/hooks/useScrollAnimate'
import { useCountUp } from '@/hooks/useCountUp'
import { api } from '@/lib/api'

// ── Icons ─────────────────────────────────────────────────────────
const SERVICE_ICONS: Record<string, string> = {
  neighbourhood: '\uD83C\uDFD8\uFE0F',
  memorial: '\uD83D\uDD6F\uFE0F',
  social: '\uD83E\uDD1D',
  route: '\uD83D\uDCCD',
  trails: '\uD83C\uDF32',
  timetravel: '\u23F3',
  pulse: '\u26A1',
  journal: '\uD83D\uDCD3',
}

const STEP_ICONS = ['\uD83D\uDCCC', '\uD83D\uDD0D', '\uD83C\uDF10']

// ── Stat counter ──────────────────────────────────────────────────
function StatCounter({ value, label, suffix = '+' }: { value: number; label: string; suffix?: string }) {
  const { ref, display } = useCountUp(value, 2000, suffix)
  return (
    <div className="about-stat" data-animate data-delay="100">
      <div className="about-stat-val" ref={ref as React.RefObject<HTMLDivElement>}>{display}</div>
      <div className="about-stat-lbl">{label}</div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────
export function AboutPage() {
  const { t } = useTranslation()
  useScrollAnimate()
  const [ctaEmail, setCtaEmail] = useState('')
  const [ctaStatus, setCtaStatus] = useState<'idle' | 'sending' | 'done' | 'error'>('idle')

  const handleSubscribe = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ctaEmail.trim()) return
    setCtaStatus('sending')
    try {
      await api.post('/newsletter/subscribe', { email: ctaEmail })
      setCtaStatus('done')
      setCtaEmail('')
    } catch {
      setCtaStatus('error')
    }
  }

  // Re-trigger scroll animate on mount
  useEffect(() => {
    const targets = document.querySelectorAll('[data-animate]')
    const observer = new IntersectionObserver(
      entries => entries.forEach(entry => {
        if (entry.isIntersecting) {
          const el = entry.target as HTMLElement
          const delay = el.dataset.delay ? parseInt(el.dataset.delay) : 0
          setTimeout(() => el.classList.add('visible'), delay)
          observer.unobserve(el)
        }
      }),
      { threshold: 0.12 },
    )
    targets.forEach(el => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  const serviceKeys = ['neighbourhood', 'memorial', 'social', 'route', 'trails', 'timetravel', 'pulse', 'journal'] as const
  const sourceKeys = ['whereqcloud', 'osm', 'feeds'] as const

  return (
    <div className="about-page">

      {/* ── Hero ────────────────────────────────────── */}
      <section className="about-hero">
        <div className="about-hero-inner" data-animate>
          <span className="about-badge">{t('hero.badge')}</span>
          <h1>
            {t('hero.title.line1')}<br />
            <span className="accent">{t('hero.title.line2')}</span>
          </h1>
          <p className="about-hero-sub">{t('hero.subtitle')}</p>
          <div className="about-hero-actions">
            <Link to="/" className="about-btn primary">{t('hero.cta.primary')}</Link>
            <button className="about-btn secondary">{t('hero.cta.secondary')}</button>
          </div>
        </div>
      </section>

      {/* ── Services ────────────────────────────────── */}
      <section className="about-section">
        <div className="about-section-hd" data-animate>
          <span className="about-tag">{t('services.tag')}</span>
          <h2>{t('services.title')}</h2>
          <p>{t('services.subtitle')}</p>
        </div>
        <div className="about-grid">
          {serviceKeys.map((key, i) => (
            <div key={key} className="about-card" data-animate data-delay={String(i * 60)}>
              <span className="about-card-icon">{SERVICE_ICONS[key]}</span>
              <h3>{t(`services.${key}.title`)}</h3>
              <p>{t(`services.${key}.desc`)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Spotlight ───────────────────────────────── */}
      <section className="about-section about-spotlight-section">
        <div className="about-spotlight" data-animate>
          <div className="about-spotlight-text">
            <span className="about-tag">{t('spotlight.tag')}</span>
            <h2>{t('spotlight.title')}</h2>
            <p>{t('spotlight.subtitle')}</p>
            <ul className="about-features">
              {(t('spotlight.features', { returnObjects: true }) as string[]).map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
            <Link to="/guides" className="about-btn primary">{t('spotlight.cta')}</Link>
          </div>
          <div className="about-spotlight-visual">
            <div className="about-score-demo">
              <div className="about-score-bar" style={{ '--w': '92%', '--c': 'var(--accent)' } as React.CSSProperties}>
                <span>Walk Score</span><span>92</span>
              </div>
              <div className="about-score-bar" style={{ '--w': '85%', '--c': 'var(--info)' } as React.CSSProperties}>
                <span>Transit</span><span>85</span>
              </div>
              <div className="about-score-bar" style={{ '--w': '78%', '--c': 'var(--success)' } as React.CSSProperties}>
                <span>Bike</span><span>78</span>
              </div>
              <div className="about-score-bar" style={{ '--w': '88%', '--c': 'var(--warn)' } as React.CSSProperties}>
                <span>Green</span><span>88</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── How It Works ────────────────────────────── */}
      <section className="about-section">
        <div className="about-section-hd" data-animate>
          <span className="about-tag">{t('howitworks.tag')}</span>
          <h2>{t('howitworks.title')}</h2>
        </div>
        <div className="about-steps">
          {(t('howitworks.steps', { returnObjects: true }) as { title: string; desc: string }[]).map((step, i) => (
            <div key={i} className="about-step" data-animate data-delay={String(i * 120)}>
              <span className="about-step-num">{STEP_ICONS[i]}</span>
              <h3>{step.title}</h3>
              <p>{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Data sources ───────────────────────────── */}
      <section className="about-section">
        <div className="about-section-hd" data-animate>
          <span className="about-tag">{t('datasource.tag')}</span>
          <h2>{t('datasource.title')}</h2>
          <p>{t('datasource.subtitle')}</p>
        </div>
        <div className="about-grid">
          {sourceKeys.map((key, i) => (
            <div key={key} className="about-card" data-animate data-delay={String(i * 60)}>
              <h3>{t(`datasource.${key}.title`)}</h3>
              <p>{t(`datasource.${key}.desc`)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Stats ───────────────────────────────────── */}
      <section className="about-section about-stats-section">
        <div className="about-section-hd" data-animate>
          <span className="about-tag">{t('stats.tag')}</span>
          <h2>{t('stats.title')}</h2>
        </div>
        <div className="about-stats">
          <StatCounter value={125000} label={t('stats.items.places')} />
          <StatCounter value={48000} label={t('stats.items.users')} />
          <StatCounter value={52} label={t('stats.items.countries')} />
          <StatCounter value={340000} label={t('stats.items.stories')} />
        </div>
      </section>

      {/* ── CTA ─────────────────────────────────────── */}
      <section className="about-section about-cta-section">
        <div className="about-cta" data-animate>
          <span className="about-tag">{t('cta.tag')}</span>
          <h2>{t('cta.title')}</h2>
          <p>{t('cta.subtitle')}</p>
          <form className="about-cta-form" onSubmit={handleSubscribe}>
            <input
              type="email"
              placeholder={t('cta.placeholder')}
              value={ctaEmail}
              onChange={e => { setCtaEmail(e.target.value); setCtaStatus('idle') }}
              required
            />
            <button type="submit" className="about-btn primary" disabled={ctaStatus === 'sending'}>
              {ctaStatus === 'sending' ? '...' : ctaStatus === 'done' ? '\u2713' : t('cta.button')}
            </button>
          </form>
          {ctaStatus === 'done' && <p style={{ color: 'var(--success)', fontSize: 13, marginTop: 8 }}>Subscribed!</p>}
          {ctaStatus === 'error' && <p style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>Already subscribed or invalid email.</p>}
        </div>
      </section>

    </div>
  )
}
