export interface HazardPin {
  id: number
  type: string        // accident | closure | police | weather | hazard | other
  severity: string    // low | med | high
  title: string
  lat: number
  lng: number
  confirmations: number
  created_at: string
  expires_at: string
}

export interface HazardCreate {
  type: string
  severity: string
  title: string
  description?: string
  latitude: number
  longitude: number
}
