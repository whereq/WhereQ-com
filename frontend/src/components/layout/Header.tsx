import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import { useTheme } from '@/contexts/ThemeContext'
import { useMapContext } from '@/contexts/MapContext'
import { useAuth } from '@/contexts/AuthContext'
import { Logo } from '@/components/ui/Logo'
import { SearchModal } from '@/components/search/SearchModal'
import { NotificationPanel } from '@/components/notifications/NotificationPanel'
import { BsEmojiNeutral, BsEmojiSmile } from 'react-icons/bs'
import { FaArrowRightToBracket, FaArrowRightFromBracket } from 'react-icons/fa6'
import i18n from '@/i18n'

// ── tiny icon helpers ──────────────────────────────────────────
const IcSearch = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
  </svg>
)
const IcSun = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
  </svg>
)
const IcMoon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
)
const IcGlobe = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20" />
  </svg>
)
const IcChevDown = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="m6 9 6 6 6-6" />
  </svg>
)
const IcMenu = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M4 6h16M4 12h16M4 18h16" />
  </svg>
)
function Flag({ code }: { code: string }) {
  const styles: Record<string, string> = {
    en: 'linear-gradient(180deg, #00247D 0%, #00247D 33%, #fff 33% 38%, #CF142B 38% 62%, #fff 62% 67%, #00247D 67%)',
    zh: 'linear-gradient(180deg, #DE2910 0%, #DE2910 100%)',
    fr: 'linear-gradient(90deg, #002654 0 33%, #fff 33% 66%, #ED2939 66%)',
  }
  return <span className="flag" style={{ background: styles[code] || styles.en }} />
}

function LocaleSwitcher() {
  const [open, setOpen] = useState(false)
  const currentLocale = i18n.language?.split('-')[0] || 'en'
  const names: Record<string, string> = { en: 'English', zh: '中文', fr: 'Français' }
  const codes = ['en', 'zh', 'fr']

  return (
    <div className="locale">
      <button className="locale-btn" onClick={() => setOpen(!open)}>
        <IcGlobe />
        <span style={{ textTransform: 'uppercase', fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '.08em' }}>
          {currentLocale === 'zh' ? 'CN' : currentLocale.toUpperCase()}
        </span>
        <IcChevDown />
      </button>
      {open && (
        <div className="locale-menu">
          {codes.map((c) => (
            <button
              key={c}
              className={currentLocale === c ? 'on' : ''}
              onClick={() => { i18n.changeLanguage(c); setOpen(false) }}
            >
              <Flag code={c} />
              <span>{names[c]}</span>
              <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10, opacity: 0.5 }}>
                {c === 'zh' ? 'CN' : c.toUpperCase()}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const NAV_ROUTES = [
  { key: 'map', path: '/' },
  { key: 'schools', path: '/schools' },
  { key: 'guides', path: '/guides' },
  { key: 'memorials', path: '/memorials' },
  { key: 'social', path: '/social' },
  { key: 'routes', path: '/routes' },
  { key: 'cards', path: '/cards' },
] as const

export function Header() {
  const { t } = useTranslation()
  const { theme, toggleTheme } = useTheme()
  const { logoVariant, accent, sidebarCollapsed, setSidebarCollapsed, openSearch } = useMapContext()
  const { user, login, logout } = useAuth()
  const location = useLocation()

  // Cmd+K / Ctrl+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        openSearch('all')
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [openSearch])

  // Trip planner "+ Add stop" opens search in stop-picking mode.
  useEffect(() => {
    const handler = () => openSearch('stop')
    window.addEventListener('whereq:open-search-stop', handler)
    return () => window.removeEventListener('whereq:open-search-stop', handler)
  }, [openSearch])

  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)

  return (
    <>
      <header className="hdr">
        <div className="hdr-l">
          <button
            className="icon-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title="Toggle sidebar"
          >
            <IcMenu />
          </button>
          <Link className="brand" to="/">
            <Logo variant={logoVariant} accent={accent} />
            <span className="wm">whereq<span className="dot">.</span>com</span>
            <span className="tag">{t('tagline')}</span>
          </Link>
        </div>

        <div className="hdr-c">
          <div
            className={`search${user ? '' : ' locked'}`}
            onClick={() => openSearch('all')}
            style={{ cursor: 'pointer' }}
          >
            <IcSearch />
            <span style={{ color: 'var(--muted)', fontSize: 12 }}>
              {user ? t('search.placeholder') : t('search.locked', 'Sign in to search')}
            </span>
            {user ? <kbd>⌘K</kbd> : <span className="search-lock">🔒</span>}
          </div>
          <nav className="nav" style={{ marginLeft: 8 }}>
            {NAV_ROUTES.map(({ key, path }) => (
              <Link
                key={key}
                to={path}
                className={isActive(path) ? 'active' : ''}
              >
                {t(`nav.${key}`)}
              </Link>
            ))}
          </nav>
        </div>

        <div className="hdr-r">
          <LocaleSwitcher />
          <button
            className="icon-btn"
            onClick={toggleTheme}
            title="Toggle theme"
          >
            {theme === 'dark' ? <IcSun /> : <IcMoon />}
          </button>
          <NotificationPanel />
          {user ? (
            <>
              <span className="hdr-user" title={user.displayName || user.email}>
                {user.avatar
                  ? <img className="hdr-avatar" src={user.avatar} alt="" referrerPolicy="no-referrer" />
                  : <BsEmojiSmile size={18} />}
              </span>
              <button className="icon-btn" title={t('signout')} onClick={() => logout()}>
                <FaArrowRightFromBracket size={15} />
              </button>
            </>
          ) : (
            <>
              <span className="hdr-user" title={t('guest')}>
                <BsEmojiNeutral size={18} />
              </span>
              <button className="icon-btn" title={t('signin')} onClick={() => login()}>
                <FaArrowRightToBracket size={15} />
              </button>
            </>
          )}
        </div>
      </header>

      <SearchModal />
    </>
  )
}
