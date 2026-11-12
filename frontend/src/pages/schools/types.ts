// Types mirroring the /api/schools read API.

export interface BoardOut {
  id: number
  slug: string
  name: string
  type: string | null
  region: string | null
}

export interface SchoolSummary {
  id: number
  name: string
  type: string | null
  province: string | null
  region: string | null
  city: string | null
  lat: number | null
  lng: number | null
  hs_score: number | null
  hs_rank: number | null
  hs_rank_total: number | null
  grade_range: string | null
  board: BoardOut | null
  programs: string[]
  has_boundary: boolean
}

export interface ScoreOut {
  year: number
  rank: number | null
  rank_total: number | null
  rank_score: number | null
  avg_exam_mark: number | null
}

export interface EqaoOut {
  grade: number
  year_mark: string | null
  rank: number | null
  total: number | null
  last5_avg: number | null
}

export interface SchoolDetail extends SchoolSummary {
  status: string | null
  address: string | null
  municipality: string | null
  phone: string | null
  phone2: string | null
  fax: string | null
  website_url: string | null
  boundary_pdf_url: string | null
  hs_name: string | null
  hs_board_type: string | null
  hs_school_type: string | null
  hs_score_year: number | null
  hs_score_average: number | null
  hs_rank_year: number | null
  feeder_schools: unknown
  scores: ScoreOut[]
  eqao: EqaoOut[]
  boundary_geojson: GeoMultiPolygon | null
}

export interface GeoMultiPolygon {
  type: 'MultiPolygon'
  coordinates: number[][][][] // [polygon][ring][point][lng,lat]
}

export interface PaginatedSchools {
  total: number
  page: number
  page_size: number
  items: SchoolSummary[]
}

export interface MapPin {
  id: number
  name: string
  lat: number
  lng: number
  type: string | null
  board_type: string | null
  hs_score: number | null
  has_boundary: boolean
}

export interface CatchmentHit {
  id: number
  name: string
  type: string | null
  board: string | null
  polygon_index: number
}

export interface TaxItem {
  id: string
  name: string
  school_count?: number
  enabled?: boolean
  province?: string
}

export interface TaxonomyBoard {
  slug: string
  name: string
  type: string | null
  region: string | null
  province: string
  school_count: number
}

export interface Taxonomy {
  provinces: TaxItem[]
  regions: TaxItem[]
  boards: TaxonomyBoard[]
  types: TaxItem[]
  board_types: TaxItem[]
  programs: TaxItem[]
}

export interface SchoolFilters {
  country: string
  province: string
  region: string
  board: string
  type: string
  board_type: string
  program: string
}

export const EMPTY_FILTERS: SchoolFilters = {
  country: 'CA', province: 'ON', region: '', board: '', type: '', board_type: '', program: '',
}
