import { useTranslation } from 'react-i18next'

const LANGS = [
  { code: 'en', label: 'EN' },
  { code: 'zh', label: '中文' },
  { code: 'fr', label: 'FR' },
]

export function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const current = i18n.language?.split('-')[0] ?? 'en'

  return (
    <div className="lang-switcher" role="group" aria-label="Language selector">
      {LANGS.map(lang => (
        <button
          key={lang.code}
          className={`lang-btn${current === lang.code ? ' active' : ''}`}
          onClick={() => i18n.changeLanguage(lang.code)}
          aria-label={lang.label}
          aria-pressed={current === lang.code}
        >
          {lang.label}
        </button>
      ))}
    </div>
  )
}
