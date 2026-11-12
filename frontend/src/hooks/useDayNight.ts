import { useEffect, useState } from 'react'

// Solar-altitude calculation (SunCalc's getPosition core) — no API, no deps.
// Returns true when the sun is above the horizon at (lat,lng,now), i.e. daytime.
const rad = Math.PI / 180
const dayMs = 1000 * 60 * 60 * 24
const J1970 = 2440588
const J2000 = 2451545
const e = rad * 23.4397 // obliquity of the ecliptic

function toDays(date: Date): number { return date.valueOf() / dayMs - 0.5 + J1970 - J2000 }

export function isDaytime(date: Date, lat: number, lng: number): boolean {
  const lw = rad * -lng
  const phi = rad * lat
  const d = toDays(date)
  const M = rad * (357.5291 + 0.98560028 * d) // solar mean anomaly
  const C = rad * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M))
  const L = M + C + rad * 102.9372 + Math.PI // ecliptic longitude
  const dec = Math.asin(Math.sin(e) * Math.sin(L)) // declination
  const ra = Math.atan2(Math.sin(L) * Math.cos(e), Math.cos(L)) // right ascension
  const H = rad * (280.16 + 360.9856235 * d) - lw - ra // hour angle
  const altitude = Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H))
  return altitude > -0.833 * rad // above horizon (with refraction) → day
}

/** Day/night for a location, re-checked every minute so it flips at sunrise/sunset.
 *  Defaults to Toronto. */
export function useDayNight(lat = 43.6532, lng = -79.3832): boolean {
  const [day, setDay] = useState(() => isDaytime(new Date(), lat, lng))
  useEffect(() => {
    const tick = () => setDay(isDaytime(new Date(), lat, lng))
    tick()
    const id = window.setInterval(tick, 60_000)
    return () => window.clearInterval(id)
  }, [lat, lng])
  return day
}
