import { useTranslation } from 'react-i18next'

export function Hero() {
  const { t } = useTranslation()

  return (
    <section className="hero" id="hero">
      <div className="hero-bg" aria-hidden="true" />
      <div className="hero-glow hero-glow-1" aria-hidden="true" />
      <div className="hero-glow hero-glow-2" aria-hidden="true" />

      <div className="pulse-container" aria-hidden="true">
        <div className="pulse-ring" />
        <div className="pulse-ring" />
        <div className="pulse-ring" />
      </div>

      <div className="floating-cards" aria-hidden="true">
        <div className="float-card">
          <div className="float-card-dot" />
          <span>📍 Eiffel Tower • Paris</span>
        </div>
        <div className="float-card">
          <div className="float-card-dot" />
          <span>🏔️ Mount Fuji • Japan</span>
        </div>
        <div className="float-card">
          <div className="float-card-dot" />
          <span>🌊 Bondi Beach • Sydney</span>
        </div>
        <div className="float-card">
          <div className="float-card-dot" />
          <span>🗽 Manhattan • New York</span>
        </div>
      </div>

      <div className="container">
        <div className="hero-content" data-animate>

          <div className="hero-badge">
            <span className="badge-dot" aria-hidden="true" />
            <span>{t('hero.badge')}</span>
          </div>

          <h1>
            <span>{t('hero.title.line1')}</span>
            <span className="line2">{t('hero.title.line2')}</span>
          </h1>

          <p className="hero-subtitle">{t('hero.subtitle')}</p>

          <div className="hero-ctas">
            <a href="#services" className="btn btn-primary">
              {t('hero.cta.primary')}
            </a>
            <a href="#" className="btn btn-ghost">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M8 5v14l11-7z" />
              </svg>
              {t('hero.cta.secondary')}
            </a>
          </div>

          <div className="hero-stats" aria-label="Platform statistics">
            <div className="hero-stat">
              <div className="hero-stat-number">2M+</div>
              <div className="hero-stat-label">{t('hero.stat.places')}</div>
            </div>
            <div className="hero-stat">
              <div className="hero-stat-number">500K+</div>
              <div className="hero-stat-label">{t('hero.stat.users')}</div>
            </div>
            <div className="hero-stat">
              <div className="hero-stat-number">150+</div>
              <div className="hero-stat-label">{t('hero.stat.countries')}</div>
            </div>
          </div>

        </div>
      </div>
    </section>
  )
}
