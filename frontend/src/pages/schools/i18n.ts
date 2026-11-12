// School-page strings, adapted from the design's SC_I18N to real fields
// (rank/EQAO/programs instead of enrollment/founded/languages). Keyed to the
// app locales en / zh / fr (the design's "cn" → "zh").

export type ScLocale = 'en' | 'zh' | 'fr'

export interface ScStrings {
  brand: string; tagline: string; backWww: string
  modeMap: string; modeList: string
  searchPh: string; filters: string; clear: string; searchGo: string
  f: { country: string; province: string; region: string; board: string; type: string; boardType: string; program: string; any: string }
  showBoundary: string; clusterToggle: string
  selectSchool: string; selectHint: string
  near: string; results: string; noResults: string
  table: { name: string; type: string; board: string; region: string; score: string; rank: string; grades: string }
  page: string; of: string; rows: string; prev: string; next: string
  detail: {
    back: string; overview: string; catchment: string; contact: string; grades: string; score: string; rank: string
    board: string; boardType: string; region: string; programs: string; viewOnMap: string; noLocation: string; address: string; phone: string
    boundaryYes: string; boundaryNo: string; website: string; compare: string; save: string
    scoresTrend: string; eqao: string; noScore: string; year: string
  }
  loc: { locating: string; toronto: string; you: string }
  zoomHint: string
  atHere: string; atHereHint: string
  auth: { signIn: string; signOut: string; boundaryGated: string; catchmentGated: string }
}

export const SC_I18N: Record<ScLocale, ScStrings> = {
  en: {
    brand: 'Schools', tagline: 'FIND · COMPARE · ZONE', backWww: 'whereq.com',
    modeMap: 'Map', modeList: 'List',
    searchPh: 'Search schools by name…', filters: 'Filters', clear: 'Clear all', searchGo: 'Search',
    f: { country: 'Country', province: 'Province', region: 'Region', board: 'School board', type: 'Level', boardType: 'Board type', program: 'Program', any: 'Any' },
    showBoundary: 'Show school boundaries', clusterToggle: 'Cluster at low zoom',
    selectSchool: 'Select a school', selectHint: 'Search above or click a pin to see details here.',
    near: 'Schools in view', results: 'results', noResults: 'No schools match your filters.',
    table: { name: 'School', type: 'Level', board: 'Board', region: 'Region', score: 'Score', rank: 'Rank', grades: 'Grades' },
    page: 'Page', of: 'of', rows: 'per page', prev: 'Prev', next: 'Next',
    detail: {
      back: 'Back to results', overview: 'Overview', catchment: 'Catchment', contact: 'Contact', grades: 'Grades', score: 'Rating', rank: 'Rank',
      board: 'Board', boardType: 'Board type', region: 'Region', programs: 'Programs', viewOnMap: 'View on map', noLocation: 'Location data unavailable for this school', address: 'Address', phone: 'Phone',
      boundaryYes: 'Boundary data available', boundaryNo: 'No boundary data on file', website: 'Website', compare: 'Compare', save: 'Save school',
      scoresTrend: 'Rating history', eqao: 'EQAO', noScore: 'No rating', year: 'Year',
    },
    loc: { locating: 'Locating…', toronto: 'Toronto Downtown', you: 'Your location' },
    zoomHint: 'Zoom in to reveal more schools',
    atHere: 'Catchments here', atHereHint: 'Click the map to find which school zones cover a point.',
    auth: { signIn: 'Sign in', signOut: 'Sign out', boundaryGated: 'Sign in to view school boundaries', catchmentGated: 'Sign in to look up catchments' },
  },
  zh: {
    brand: '学校', tagline: '查找 · 对比 · 学区', backWww: 'whereq.com',
    modeMap: '地图', modeList: '列表',
    searchPh: '按名称搜索学校…', filters: '筛选', clear: '清除全部', searchGo: '搜索',
    f: { country: '国家', province: '省份', region: '地区', board: '教育局', type: '阶段', boardType: '类型', program: '项目', any: '任意' },
    showBoundary: '显示学区边界', clusterToggle: '低缩放时聚合',
    selectSchool: '选择学校', selectHint: '在上方搜索或点击地图标记查看详情。',
    near: '视野内学校', results: '个结果', noResults: '没有符合条件的学校。',
    table: { name: '学校', type: '阶段', board: '教育局', region: '地区', score: '评分', rank: '排名', grades: '年级' },
    page: '第', of: '页 / 共', rows: '每页', prev: '上一页', next: '下一页',
    detail: {
      back: '返回结果', overview: '概览', catchment: '学区', contact: '联系方式', grades: '年级', score: '评分', rank: '排名',
      board: '教育局', boardType: '类型', region: '地区', programs: '项目', viewOnMap: '在地图查看', noLocation: '暂无该学校的位置信息', address: '地址', phone: '电话',
      boundaryYes: '有学区边界数据', boundaryNo: '暂无学区边界数据', website: '网站', compare: '对比', save: '收藏学校',
      scoresTrend: '评分历史', eqao: 'EQAO', noScore: '暂无评分', year: '年份',
    },
    loc: { locating: '定位中…', toronto: '多伦多市中心', you: '你的位置' },
    zoomHint: '放大以显示更多学校',
    atHere: '此处学区', atHereHint: '点击地图查看某点所属的学校学区。',
    auth: { signIn: '登录', signOut: '退出', boundaryGated: '登录后查看学区边界', catchmentGated: '登录后查询所属学区' },
  },
  fr: {
    brand: 'Écoles', tagline: 'TROUVER · COMPARER · ZONE', backWww: 'whereq.com',
    modeMap: 'Carte', modeList: 'Liste',
    searchPh: 'Rechercher une école par nom…', filters: 'Filtres', clear: 'Tout effacer', searchGo: 'Rechercher',
    f: { country: 'Pays', province: 'Province', region: 'Région', board: 'Conseil scolaire', type: 'Niveau', boardType: 'Type', program: 'Programme', any: 'Tous' },
    showBoundary: 'Afficher les limites', clusterToggle: 'Regrouper à bas zoom',
    selectSchool: 'Sélectionner une école', selectHint: 'Recherchez ci-dessus ou cliquez un repère.',
    near: 'Écoles visibles', results: 'résultats', noResults: 'Aucune école ne correspond.',
    table: { name: 'École', type: 'Niveau', board: 'Conseil', region: 'Région', score: 'Note', rank: 'Rang', grades: 'Niveaux' },
    page: 'Page', of: 'sur', rows: 'par page', prev: 'Préc.', next: 'Suiv.',
    detail: {
      back: 'Retour aux résultats', overview: 'Aperçu', catchment: 'Secteur', contact: 'Contact', grades: 'Niveaux', score: 'Note', rank: 'Rang',
      board: 'Conseil', boardType: 'Type', region: 'Région', programs: 'Programmes', viewOnMap: 'Voir sur la carte', noLocation: 'Localisation indisponible pour cette école', address: 'Adresse', phone: 'Téléphone',
      boundaryYes: 'Limites disponibles', boundaryNo: 'Aucune limite enregistrée', website: 'Site web', compare: 'Comparer', save: 'Enregistrer',
      scoresTrend: 'Historique des notes', eqao: 'EQAO', noScore: 'Pas de note', year: 'Année',
    },
    loc: { locating: 'Localisation…', toronto: 'Centre-ville de Toronto', you: 'Votre position' },
    zoomHint: 'Zoomez pour révéler plus d’écoles',
    atHere: 'Secteurs ici', atHereHint: 'Cliquez la carte pour voir les secteurs scolaires d’un point.',
    auth: { signIn: 'Se connecter', signOut: 'Se déconnecter', boundaryGated: 'Connectez-vous pour voir les limites', catchmentGated: 'Connectez-vous pour trouver les secteurs' },
  },
}

export function scLocale(appLocale: string): ScLocale {
  if (appLocale.startsWith('zh') || appLocale === 'cn') return 'zh'
  if (appLocale.startsWith('fr')) return 'fr'
  return 'en'
}
