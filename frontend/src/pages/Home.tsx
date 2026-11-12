import { Sidebar } from '@/components/layout/Sidebar'
import { MapArea } from '@/components/map/MapArea'
import { useMapContext } from '@/contexts/MapContext'

export function Home() {
  const { sidebarCollapsed } = useMapContext()

  return (
    <main className={`main${sidebarCollapsed ? ' collapsed' : ''}`}>
      <Sidebar />
      <MapArea />
    </main>
  )
}
