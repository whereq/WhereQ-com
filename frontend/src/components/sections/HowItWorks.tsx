import { useTranslation } from 'react-i18next'

const STEPS = [
  { key: 'step1', emoji: '📍', delay: 100 },
  { key: 'step2', emoji: '🔍', delay: 250 },
  { key: 'step3', emoji: '🌐', delay: 400 },
]

export function HowItWorks() {
  const { t } = useTranslation()

  return (
    <section className="howitworks" id="howitworks">
      <div className="container">

        <div className="section-header" data-animate>
          <div className="section-tag">{t('howitworks.tag')}</div>
          <h2>{t('howitworks.title')}</h2>
        </div>

        <div className="steps-grid">
          {STEPS.map((step, i) => (
            <div key={step.key} className="step-card" data-animate data-delay={String(step.delay)}>
              <div className="step-icon" aria-hidden="true">
                <span style={{ fontSize: '2rem' }}>{step.emoji}</span>
                <div className="step-number">{i + 1}</div>
              </div>
              <h3>{t(`howitworks.${step.key}.title`)}</h3>
              <p>{t(`howitworks.${step.key}.desc`)}</p>
            </div>
          ))}
        </div>

      </div>
    </section>
  )
}
