export type MapStyle = 'streets' | 'satellite' | 'terrain' | 'transit'
export type LogoVariant = 'globe' | 'pin' | 'compass' | 'mono'
export type SchoolLevel = 'elem' | 'k8' | 'middle' | 'high' | 'college' | 'uni'
export type PinKind =
  | 'me' | 'memorial' | 'friend' | 'hazard' | 'poi'
  | 'saved' | 'school' | 'pharmacy' | 'clinic' | 'plaza' | 'library'
export type PoiCat = 'coffee' | 'food' | 'parking' | 'fuel'
export type FriendStatus = 'active' | 'idle' | 'off'

export interface MapPin {
  id: string
  x: number
  y: number
  lat: number
  lng: number
  kind: PinKind
  title?: string
  sub?: string
  story?: string
  name?: string
  initial?: string
  status?: FriendStatus
  cat?: PoiCat
  color?: string
  level?: SchoolLevel
  grade?: string
}

export interface MapFilters {
  friends: boolean
  memorial: boolean
  hazards: boolean
  guides: boolean
  routes: boolean
  weather: boolean
  /** The administrative areas layer (cities, wards, neighbourhoods). */
  areas: boolean
}

export interface MapEssentials {
  schools: boolean
  pharmacies: boolean
  clinics: boolean
  plazas: boolean
  libraries: boolean
}

export interface CityData {
  W: number
  H: number
  riverPath: string
  parks: string[]
  majorRoads: string[]
  highway: string
  minorRoads: string[]
  buildings: { x: number; y: number; w: number; h: number; t: number }[]
  labels: { x: number; y: number; txt: string; sz: number; hi?: boolean; road?: boolean }[]
}
