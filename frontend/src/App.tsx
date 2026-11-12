import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { APIProvider } from '@vis.gl/react-google-maps'
import { GlobalScrollbar } from '@whereq/react'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { MapProvider } from '@/contexts/MapContext'
import { PlacesProvider } from '@/contexts/PlacesContext'
import { RouteProvider } from '@/contexts/RouteContext'
import { FriendsProvider } from '@/contexts/FriendsContext'
import { AuthProvider } from '@/contexts/AuthContext'
import { Layout } from '@/components/layout/Layout'
import { ErrorToaster } from '@/components/ui/ErrorToaster'
import { reportError } from '@/lib/errorBus'
import { Home } from '@/pages/Home'
import { GuidesPage } from '@/pages/GuidesPage'
import { MemorialsPage } from '@/pages/MemorialsPage'
import { SocialPage } from '@/pages/SocialPage'
import { RoutesPage } from '@/pages/RoutesPage'
import { CardsPage } from '@/pages/CardsPage'
import { SchoolsPage } from '@/pages/schools/SchoolsPage'
import { AboutPage } from '@/pages/AboutPage'
import '@/i18n'

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? ''

export default function App() {
  return (
    <APIProvider
      apiKey={GOOGLE_MAPS_API_KEY}
      onError={error => reportError(String(error), { code: 'toast.mapsFailed' })}
    >
      <ThemeProvider>
        <AuthProvider>
          <MapProvider>
            <PlacesProvider>
              <RouteProvider>
              <FriendsProvider>
              <BrowserRouter>
                <Routes>
                  {/* Standalone full-screen app (own header) — no main Layout */}
                  <Route path="/schools" element={<SchoolsPage />} />
                  <Route
                    path="*"
                    element={
                      <Layout>
                        <Routes>
                          <Route path="/" element={<Home />} />
                          <Route path="/guides" element={<GuidesPage />} />
                          <Route path="/memorials" element={<MemorialsPage />} />
                          <Route path="/social" element={<SocialPage />} />
                          <Route path="/routes" element={<RoutesPage />} />
                          <Route path="/cards" element={<CardsPage />} />
                          <Route path="/about" element={<AboutPage />} />
                        </Routes>
                      </Layout>
                    }
                  />
                </Routes>
              </BrowserRouter>
              </FriendsProvider>
              </RouteProvider>
            </PlacesProvider>
          </MapProvider>
        </AuthProvider>
        <ErrorToaster />
        {/* The shared scrollbar, app-wide: every native scrollbar in the app
            gets the same thin look, and it follows the theme. */}
        <GlobalScrollbar theme="auto" size={6} />
      </ThemeProvider>
    </APIProvider>
  )
}