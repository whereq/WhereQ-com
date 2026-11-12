import { useTranslation } from 'react-i18next'

function CheckIcon() {
  return (
    <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="2,6 5,9 10,3" />
    </svg>
  )
}

export function Spotlight() {
  const { t } = useTranslation()

  const features = [
    t('spotlight.feature1'),
    t('spotlight.feature2'),
    t('spotlight.feature3'),
    t('spotlight.feature4'),
  ]

  return (
    <section className="spotlight" id="spotlight">
      <div className="container">
        <div className="spotlight-inner">

          <div className="spotlight-text" data-animate>
            <div className="section-tag">{t('spotlight.tag')}</div>
            <h2>{t('spotlight.title')}</h2>
            <p>{t('spotlight.subtitle')}</p>

            <ul className="feature-list" role="list">
              {features.map((f, i) => (
                <li key={i} className="feature-item">
                  <span className="feature-check" aria-hidden="true">
                    <CheckIcon />
                  </span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>

            <a href="#" className="btn btn-primary">
              {t('spotlight.cta')}
            </a>
          </div>

          <div className="spotlight-visual" data-animate data-delay="200" aria-hidden="true">
            <div className="card-stack">

              <div className="neighbourhood-card nc-1">
                <div className="card-header-bar" />
                <div className="card-body">
                  <div className="card-location-row">
                    <span className="card-loc-name">East Village</span>
                    <span className="card-score">92</span>
                  </div>
                  <div className="card-bars">
                    <div className="card-bar-row">
                      <span style={{ width: 70 }}>Safety</span>
                      <div className="card-bar-track"><div className="card-bar-fill" style={{ width: '88%' }} /></div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="neighbourhood-card nc-2">
                <div className="card-header-bar" />
                <div className="card-body">
                  <div className="card-location-row">
                    <span className="card-loc-name">Marais District</span>
                    <span className="card-score">96</span>
                  </div>
                  <div className="card-bars">
                    <div className="card-bar-row">
                      <span style={{ width: 70 }}>Walkable</span>
                      <div className="card-bar-track"><div className="card-bar-fill" style={{ width: '94%' }} /></div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="neighbourhood-card nc-3">
                <div className="card-header-bar" />
                <div className="card-body">
                  <div className="card-location-row">
                    <span className="card-loc-name">Shoreditch, London</span>
                    <span className="card-score">94</span>
                  </div>
                  <div className="card-tags">
                    {['Trendy', 'Arts', 'Food', 'Walkable'].map(tag => (
                      <span key={tag} className="card-tag">{tag}</span>
                    ))}
                  </div>
                  <div className="card-bars">
                    {[['Safety', '90%', '90'], ['Transit', '95%', '95'], ['Food', '97%', '97'], ['Schools', '82%', '82']].map(
                      ([label, width, score]) => (
                        <div key={label} className="card-bar-row">
                          <span style={{ width: 70, flexShrink: 0 }}>{label}</span>
                          <div className="card-bar-track"><div className="card-bar-fill" style={{ width }} /></div>
                          <span>{score}</span>
                        </div>
                      )
                    )}
                  </div>
                </div>
              </div>

            </div>
          </div>

        </div>
      </div>
    </section>
  )
}
