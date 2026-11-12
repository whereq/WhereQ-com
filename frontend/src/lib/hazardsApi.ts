import { api } from './api'
import type { HazardCreate, HazardPin } from '@/types/hazard'

export const hazardsApi = {
  map: (bbox: string) => api.get<HazardPin[]>(`/hazards/map?bbox=${encodeURIComponent(bbox)}`),
  create: (data: HazardCreate) => api.post<HazardPin>('/hazards', data),
  confirm: (id: number) => api.post<HazardPin>(`/hazards/${id}/confirm`),
}

export const HAZARD_TYPES = [
  { id: 'hazard', label: 'Hazard' },
  { id: 'accident', label: 'Accident' },
  { id: 'closure', label: 'Road closure' },
  { id: 'police', label: 'Police' },
  { id: 'weather', label: 'Weather' },
  { id: 'other', label: 'Other' },
] as const
