// Local content (news / events / stories / topics) shown on the map.

export type LocalType = 'news' | 'event' | 'story' | 'topic'

export interface LocalPin {
  id: number
  type: LocalType
  category: string
  lat: number
  lng: number
  title: string
  source_name: string | null
  event_time: string | null
  publish_time: string | null
  image_url: string | null
}

export interface LocalContentDetail {
  id: number
  type: LocalType
  category: string
  title: string
  summary: string | null
  description: string | null
  source_name: string | null
  source_url: string | null
  event_time: string | null
  event_end_time: string | null
  publish_time: string | null
  lat: number | null
  lng: number | null
  address: string | null
  city: string | null
  province: string | null
  country: string | null
  image_url: string | null
  confidence_score: number | null
  tags: string[]
  created_at: string | null
}

export interface LocalTaxItem {
  id: string
  name: string
  count: number
}

export interface LocalSourceItem {
  id: number
  slug: string
  name: string
  count: number
}

export interface LocalTaxonomy {
  types: LocalTaxItem[]
  categories: LocalTaxItem[]
  sources: LocalSourceItem[]
}

export interface LocalSearchItem {
  id: number
  type: LocalType
  category: string
  title: string
  summary: string | null
  source_name: string | null
  source_url: string | null
  lat: number | null
  lng: number | null
  city: string | null
  event_time: string | null
  publish_time: string | null
  image_url: string | null
}

export interface LocalSearchResponse {
  total: number
  results: LocalSearchItem[]
}
