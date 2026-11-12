import type { MapPin, CityData } from '@/types/map'

function makeRng(seed: number) {
  let s = (seed >>> 0)
  return () => {
    s = ((s * 1664525 + 1013904223) >>> 0)
    return s / 4294967296
  }
}

export function generateCity(seed = 42): CityData {
  const rng = makeRng(seed)
  const W = 1600, H = 900

  // River path
  const riverPts: [number, number][] = []
  for (let i = 0; i <= 12; i++) {
    const t = i / 12
    const x = -50 + t * (W + 100)
    const y = 320 + Math.sin(t * 4.2 + 0.6) * 130 + t * 100
    riverPts.push([x, y])
  }
  const riverPath = (() => {
    let d = `M ${riverPts[0][0]} ${riverPts[0][1]}`
    for (let i = 1; i < riverPts.length; i++) {
      const [px, py] = riverPts[i - 1]
      const [x, y] = riverPts[i]
      const cx = (px + x) / 2
      const cy = (py + y) / 2
      d += ` Q ${px} ${py} ${cx} ${cy}`
    }
    d += ` T ${riverPts[riverPts.length - 1][0]} ${riverPts[riverPts.length - 1][1]}`
    return d
  })()

  const parks = [
    { cx: 1180, cy: 200, r: 110, n: 9 },
    { cx: 280, cy: 720, r: 80, n: 7 },
    { cx: 720, cy: 80, r: 60, n: 6 },
  ].map(p => {
    const pts: string[] = []
    for (let i = 0; i < p.n; i++) {
      const a = (i / p.n) * Math.PI * 2 + rng() * 0.4
      const r = p.r * (0.75 + rng() * 0.5)
      pts.push(`${p.cx + Math.cos(a) * r},${p.cy + Math.sin(a) * r}`)
    }
    return pts.join(' ')
  })

  const majorRoads = [
    'M -20 470 Q 350 460 700 510 T 1620 540',
    'M 460 -20 Q 480 280 540 520 T 600 920',
    'M 1050 -20 Q 1080 220 1140 460 T 1200 920',
    'M -20 220 Q 380 240 740 200 T 1620 250',
    'M -20 720 Q 380 740 760 730 T 1620 700',
  ]
  const highway = 'M -20 600 Q 280 590 540 640 T 1080 700 T 1620 740'

  const minorRoads: string[] = []
  for (let y = 30; y < H; y += 36) {
    if (Math.abs((y - 480) % 36) < 2) continue
    const wob = (y % 72 === 0) ? 0 : 6
    minorRoads.push(`M -10 ${y + (rng() - 0.5) * wob} L ${W + 10} ${y + (rng() - 0.5) * wob}`)
  }
  for (let x = 30; x < W; x += 44) {
    const wob = (x % 88 === 0) ? 0 : 8
    minorRoads.push(`M ${x + (rng() - 0.5) * wob} -10 L ${x + (rng() - 0.5) * wob} ${H + 10}`)
  }
  for (let i = 0; i < 4; i++) {
    const ox = rng() * W
    const oy = rng() * H
    minorRoads.push(`M ${ox - 200} ${oy - 200} L ${ox + 400} ${oy + 400}`)
  }

  const buildings: { x: number; y: number; w: number; h: number; t: number }[] = []
  const ROAD_Y = [30, 66, 102, 138, 174, 210, 246, 282, 318, 354, 390, 426, 462, 498, 534, 570, 606, 642, 678, 714, 750, 786, 822, 858, 894]
  for (let yi = 0; yi < ROAD_Y.length - 1; yi++) {
    for (let x = 36; x < W - 36; x += 44) {
      const y0 = ROAD_Y[yi] + 3
      const y1 = ROAD_Y[yi + 1] - 3
      const cy = (y0 + y1) / 2
      const cx = x + 22
      const t = (cx + 50) / (W + 100)
      const ry = 320 + Math.sin(t * 4.2 + 0.6) * 130 + t * 100
      if (Math.abs(cy - ry) < 60) continue
      if (rng() > 0.78) continue
      const bw = 14 + rng() * 24
      const bh = (y1 - y0) * (0.5 + rng() * 0.45)
      const bx = x + (44 - bw) * rng()
      const by = y0 + (y1 - y0 - bh) * rng()
      buildings.push({ x: bx, y: by, w: bw, h: bh, t: rng() > 0.85 ? 1 : 0 })
    }
  }

  const labels = [
    { x: 220, y: 200, txt: 'RIVERSIDE', sz: 14 },
    { x: 1140, y: 200, txt: 'GREENBELT PARK', sz: 12 },
    { x: 800, y: 540, txt: 'OLD TOWN', sz: 18, hi: true },
    { x: 1320, y: 700, txt: 'EAST QUARTER', sz: 13 },
    { x: 340, y: 780, txt: 'SOUTHFIELD', sz: 12 },
    { x: 540, y: 380, txt: 'Hawthorne Ave', sz: 10, road: true },
    { x: 1080, y: 760, txt: 'Highway 8', sz: 10, road: true },
    { x: 920, y: 80, txt: '5th Street', sz: 10, road: true },
  ]

  return { W, H, riverPath, parks, majorRoads, highway, minorRoads, buildings, labels }
}

export const PINS: MapPin[] = [
  { id: 'me', x: 800, y: 480, lat: 37.7616, lng: -122.4356, kind: 'me' },
  { id: 'mem1', x: 900, y: 380, lat: 37.7648, lng: -122.4290, kind: 'memorial', title: 'Greybrick Theatre',
    sub: '1923 · Demolished 1978',
    story: 'Once the city\'s grandest movie house. Marlene Dietrich performed here in 1932. Today the lot is a parking garage; the marquee neon survives in a private collection.' },
  { id: 'mem2', x: 480, y: 620, lat: 37.7570, lng: -122.4420, kind: 'memorial', title: 'Old Foundry Steps' },
  { id: 'f1', x: 1100, y: 540, lat: 37.7600, lng: -122.4230, kind: 'friend', name: 'Mira', initial: 'M', status: 'active' },
  { id: 'f2', x: 620, y: 260, lat: 37.7680, lng: -122.4400, kind: 'friend', name: 'Jules', initial: 'J', status: 'active' },
  { id: 'f3', x: 1280, y: 720, lat: 37.7540, lng: -122.4180, kind: 'friend', name: 'Ren', initial: 'R', status: 'idle' },
  { id: 'h1', x: 540, y: 540, lat: 37.7600, lng: -122.4440, kind: 'hazard', title: 'Construction', sub: 'lane closure' },
  { id: 'h2', x: 1180, y: 240, lat: 37.7690, lng: -122.4210, kind: 'hazard', title: 'Police', sub: 'reported 4m ago' },
  { id: 'p1', x: 760, y: 540, lat: 37.7600, lng: -122.4370, kind: 'poi', cat: 'coffee', title: 'Pier Coffee' },
  { id: 'p2', x: 1020, y: 460, lat: 37.7625, lng: -122.4270, kind: 'poi', cat: 'food', title: 'Sato Ramen' },
  { id: 'p3', x: 380, y: 380, lat: 37.7650, lng: -122.4480, kind: 'poi', cat: 'parking', title: 'P-Garage' },
  { id: 'p4', x: 1340, y: 460, lat: 37.7625, lng: -122.4150, kind: 'poi', cat: 'fuel', title: 'Shell' },
  { id: 's1', x: 700, y: 220, lat: 37.7700, lng: -122.4390, kind: 'saved', title: 'Home', color: 'var(--accent)' },
  { id: 's2', x: 1300, y: 560, lat: 37.7590, lng: -122.4170, kind: 'saved', title: 'Studio', color: 'var(--warn)' },
  // schools
  { id: 'sch1', x: 660, y: 340, lat: 37.7660, lng: -122.4410, kind: 'school', title: 'Lincoln Elementary', sub: 'K–5 · public', grade: 'K–5', level: 'elem' },
  { id: 'sch2', x: 1080, y: 620, lat: 37.7570, lng: -122.4240, kind: 'school', title: 'Oakridge Elementary', sub: 'K–5 · charter', grade: 'K–5', level: 'elem' },
  { id: 'sch3', x: 320, y: 540, lat: 37.7600, lng: -122.4500, kind: 'school', title: 'Riverside Academy', sub: 'K–8 · private', grade: 'K–8', level: 'k8' },
  { id: 'sch4', x: 900, y: 200, lat: 37.7710, lng: -122.4300, kind: 'school', title: 'Mission Middle School', sub: '6–8 · public', grade: '6–8', level: 'middle' },
  { id: 'sch5', x: 540, y: 200, lat: 37.7710, lng: -122.4450, kind: 'school', title: 'Bay High School', sub: '9–12 · public', grade: '9–12', level: 'high' },
  { id: 'sch6', x: 1280, y: 320, lat: 37.7660, lng: -122.4160, kind: 'school', title: 'City College · East', sub: 'community · 2-yr', grade: 'CC', level: 'college' },
  { id: 'sch7', x: 1180, y: 760, lat: 37.7520, lng: -122.4200, kind: 'school', title: 'Bayview University', sub: 'public · enrollment 18k', grade: 'UNI', level: 'uni' },
  // pharmacies
  { id: 'phm1', x: 740, y: 420, lat: 37.7640, lng: -122.4380, kind: 'pharmacy', title: 'Walgreens', sub: 'open 24h' },
  { id: 'phm2', x: 1140, y: 480, lat: 37.7620, lng: -122.4220, kind: 'pharmacy', title: 'CVS Pharmacy', sub: 'closes 22:00' },
  { id: 'phm3', x: 520, y: 700, lat: 37.7545, lng: -122.4450, kind: 'pharmacy', title: 'Mission Drugs', sub: 'locally owned' },
  // clinics
  { id: 'cli1', x: 860, y: 560, lat: 37.7595, lng: -122.4320, kind: 'clinic', title: 'Mission Walk-In', sub: 'wait ≈ 18 min' },
  { id: 'cli2', x: 1220, y: 360, lat: 37.7655, lng: -122.4190, kind: 'clinic', title: 'East Quarter Urgent', sub: 'wait ≈ 42 min' },
  // plazas
  { id: 'plz1', x: 820, y: 250, lat: 37.7690, lng: -122.4350, kind: 'plaza', title: 'Cornerstone Plaza', sub: 'market · Sat 9–14' },
  { id: 'plz2', x: 980, y: 700, lat: 37.7545, lng: -122.4280, kind: 'plaza', title: 'Foundry Square', sub: 'food trucks' },
  { id: 'plz3', x: 420, y: 280, lat: 37.7680, lng: -122.4470, kind: 'plaza', title: 'Riverside Plaza', sub: 'fountain' },
  // libraries
  { id: 'lib1', x: 940, y: 460, lat: 37.7625, lng: -122.4310, kind: 'library', title: 'Mission Branch Library', sub: 'open until 20:00' },
]

export const NEIGHBORHOOD_BOUNDARY =
  'M 220 140 L 580 110 L 920 130 L 1240 180 L 1380 360 L 1380 640 L 1240 760 L 920 800 L 540 780 L 280 700 L 180 460 Z'

export const SCHOOL_CATCHMENTS: Record<string, string> = {
  sch1: 'M 460 220 L 820 230 L 880 380 L 800 520 L 540 500 L 380 380 Z',
  sch2: 'M 900 520 L 1240 540 L 1280 700 L 1100 780 L 860 720 Z',
  sch3: 'M 200 420 L 460 440 L 480 660 L 240 700 L 140 540 Z',
  sch4: 'M 700 80 L 1100 90 L 1140 280 L 940 340 L 720 300 Z',
  sch5: 'M 320 80 L 740 100 L 720 280 L 460 320 L 280 240 Z',
  sch6: 'M 1080 200 L 1380 220 L 1400 440 L 1200 460 L 1100 360 Z',
  sch7: 'M 1020 660 L 1340 680 L 1380 820 L 1180 840 L 1040 780 Z',
}

export const ROUTE_PATH = (() => {
  const pts = [[700, 220], [780, 320], [800, 480], [900, 540], [1100, 540], [1300, 560]]
  let d = `M ${pts[0][0]} ${pts[0][1]}`
  for (let i = 1; i < pts.length; i++) {
    const [px, py] = pts[i - 1]
    const [x, y] = pts[i]
    const mx = (px + x) / 2
    const my = (py + y) / 2
    d += ` Q ${px} ${py} ${mx} ${my}`
  }
  d += ` T ${pts[pts.length - 1][0]} ${pts[pts.length - 1][1]}`
  return d
})()
