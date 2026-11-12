import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export function CTASection() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (email) setSubmitted(true)
  }

  return (
    <section className="cta-section" id="cta">
      <div className="container">
        <div className="cta-inner" data-animate>

          <div className="section-tag">{t('cta.tag')}</div>
          <h2>{t('cta.title')}</h2>
          <p>{t('cta.subtitle')}</p>

          {submitted ? (
            <p style={{ color: 'var(--accent-green)', fontWeight: 600, marginTop: '1rem' }}>
              ✓ You're on the list — we'll be in touch!
            </p>
          ) : (
            <form className="cta-form" onSubmit={handleSubmit} noValidate>
              <label htmlFor="cta-email" className="sr-only">Email address</label>
              <input
                type="email"
                id="cta-email"
                className="cta-input"
                placeholder={t('cta.placeholder')}
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
              <button type="submit" className="cta-btn">
                {t('cta.button')}
              </button>
            </form>
          )}

        </div>
      </div>
    </section>
  )
}
