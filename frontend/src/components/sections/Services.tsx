import { useTranslation } from 'react-i18next'

interface ServiceDef {
  key: string
  color: string
  iconBg: string
  iconColor: string
  icon: React.ReactNode
}

const SERVICES: ServiceDef[] = [
  {
    key: 'neighbourhood', color: 'blue', iconBg: 'icon-bg-blue', iconColor: 'icon-color-blue',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <polygon points="16.24,7.76 14.12,14.12 7.76,16.24 9.88,9.88 16.24,7.76"/>
      </svg>
    ),
  },
  {
    key: 'memorial', color: 'purple', iconBg: 'icon-bg-purple', iconColor: 'icon-color-purple',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        <line x1="12" y1="6" x2="16" y2="6"/>
        <line x1="12" y1="10" x2="16" y2="10"/>
      </svg>
    ),
  },
  {
    key: 'social', color: 'pink', iconBg: 'icon-bg-pink', iconColor: 'icon-color-pink',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    ),
  },
  {
    key: 'route', color: 'orange', iconBg: 'icon-bg-orange', iconColor: 'icon-color-orange',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22,12 18,12 15,21 9,3 6,12 2,12"/>
      </svg>
    ),
  },
  {
    key: 'trails', color: 'green', iconBg: 'icon-bg-green', iconColor: 'icon-color-green',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="3,20 12,4 21,20"/>
        <line x1="12" y1="20" x2="12" y2="13"/>
      </svg>
    ),
  },
  {
    key: 'timetravel', color: 'cyan', iconBg: 'icon-bg-cyan', iconColor: 'icon-color-cyan',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12,6 12,12 16,14"/>
      </svg>
    ),
  },
  {
    key: 'pulse', color: 'red', iconBg: 'icon-bg-red', iconColor: 'icon-color-red',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22,12 18,12 15,21 9,3 6,12 2,12"/>
      </svg>
    ),
  },
  {
    key: 'journal', color: 'indigo', iconBg: 'icon-bg-indigo', iconColor: 'icon-color-indigo',
    icon: (
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>
    ),
  },
]

export function Services() {
  const { t } = useTranslation()

  return (
    <section className="services" id="services">
      <div className="container">

        <div className="section-header" data-animate>
          <div className="section-tag">{t('services.tag')}</div>
          <h2>{t('services.title')}</h2>
          <p>{t('services.subtitle')}</p>
        </div>

        <div className="services-grid">
          {SERVICES.map((svc, i) => (
            <article
              key={svc.key}
              className="service-card"
              data-color={svc.color}
              data-animate
              data-delay={String(100 + i * 50)}
            >
              <div className={`service-icon ${svc.iconBg} ${svc.iconColor}`} aria-hidden="true">
                {svc.icon}
              </div>
              <h3>{t(`services.${svc.key}.title`)}</h3>
              <p>{t(`services.${svc.key}.desc`)}</p>
              <a href="#" className="service-link">{t('services.learnmore')}</a>
            </article>
          ))}
        </div>

      </div>
    </section>
  )
}
