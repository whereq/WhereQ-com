import { useTranslation } from 'react-i18next'

const FRIENDS = [
  { init: 'M', name: 'Mira Patel', status: 'Online · Pier Coffee' },
  { init: 'J', name: 'Jules Okafor', status: 'Online · Riverside Park' },
  { init: 'R', name: 'Ren Tanaka', status: 'Idle · East Quarter' },
  { init: 'S', name: 'Sofia Lima', status: 'Last seen 2h ago' },
  { init: 'A', name: 'Alex Chen', status: 'Offline' },
  { init: 'K', name: 'Kai Williams', status: 'Online · Downtown' },
]

export function SocialPage() {
  const { t } = useTranslation()

  return (
    <main className="content-page">
      <div className="content-page-inner">
        <div className="content-page-hd">
          <h1>{t('pages.social.title')}</h1>
          <p>{t('pages.social.subtitle')}</p>
        </div>

        <div className="content-grid">
          {FRIENDS.map(f => (
            <div key={f.name} className="content-card friend-card">
              <span className="av">{f.init}</span>
              <div className="info">
                <div className="name">{f.name}</div>
                <div className="status">{f.status}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
