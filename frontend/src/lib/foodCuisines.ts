// Food sub-categories (cuisines). `id` matches the OSM `cuisine` tag value
// (stored in Place.sub), matched as a substring server-side so multi-value tags
// like "italian;pizza" still hit. Curated for the GTA; extend freely.
export interface Cuisine { id: string; label: string }

export const FOOD_CUISINES: Cuisine[] = [
  { id: 'chinese', label: 'Chinese' },
  { id: 'italian', label: 'Italian' },
  { id: 'japanese', label: 'Japanese' },
  { id: 'korean', label: 'Korean' },
  { id: 'thai', label: 'Thai' },
  { id: 'indian', label: 'Indian' },
  { id: 'vietnamese', label: 'Vietnamese' },
  { id: 'mexican', label: 'Mexican' },
  { id: 'pizza', label: 'Pizza' },
  { id: 'sushi', label: 'Sushi' },
  { id: 'burger', label: 'Burger' },
  { id: 'middle_eastern', label: 'Middle Eastern' },
]
