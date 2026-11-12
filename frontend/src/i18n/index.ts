import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import en from './locales/en.json'
import zh from './locales/zh.json'
import fr from './locales/fr.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      zh: { translation: zh },
      fr: { translation: fr },
    },
    fallbackLng: 'en',
    supportedLngs: ['en', 'zh', 'fr'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  })

// The document language has to follow the UI language, or a screen reader
// reads French content with an English voice. index.html ships lang="en" for
// the first paint; this keeps it in step afterwards.
const syncDocumentLang = (lng?: string) => {
  document.documentElement.lang = lng || 'en'
}
i18n.on('languageChanged', syncDocumentLang)
syncDocumentLang(i18n.language)

export default i18n
