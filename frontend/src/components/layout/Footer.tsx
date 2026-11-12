import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

export function Footer() {
  const { t } = useTranslation()

  return (
    <footer className="ftr">
      <span>{t('footer.copy')}</span>
      <span className="links">
        <Link to="/about">{t('footer.links.about')}</Link>
        <a href="/api/docs" target="_blank" rel="noopener noreferrer">{t('footer.links.api')}</a>
        <Link to="/about">{t('footer.links.privacy')}</Link>
        <Link to="/about">{t('footer.links.status')}</Link>
      </span>
      <span className="right">
        <span className="dot" />
        <span>{t('footer.live')}</span>
        <span style={{ opacity: 0.5 }}>· build 2026.05.24</span>
      </span>
      {/* Attribution is a licence obligation, not decoration: OSM data is
          ODbL 1.0 and Google Maps content carries its own terms. */}
      <span className="attribution">{t('footer.attribution')}</span>
    </footer>
  )
}
