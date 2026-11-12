// Type → semantic color, adapted from the design to real fields
// (school.type + board.type + programs).

export const TYPE_COLORS: Record<string, string> = {
  elementary: '#5BA5FF',
  secondary: '#FFB020',
  french: '#818CF8',   // indigo (was lavender — dropped pink family)
  catholic: '#2DD4BF', // teal (was pink — dropped pink family)
  gifted: '#4ADE80',
}

interface ColorInput {
  type?: string | null
  board_type?: string | null   // public | catholic | private
  programs?: string[]
}

function hasProgram(programs: string[] | undefined, needle: string): boolean {
  return !!programs?.some((p) => p.toLowerCase().includes(needle))
}

export function schoolColor(s: ColorInput): string {
  if (hasProgram(s.programs, 'gifted') || hasProgram(s.programs, 'pace')) return TYPE_COLORS.gifted
  if (s.board_type === 'catholic') return TYPE_COLORS.catholic
  if (hasProgram(s.programs, 'french')) return TYPE_COLORS.french
  return s.type === 'secondary' ? TYPE_COLORS.secondary : TYPE_COLORS.elementary
}

// Badges shown on a school: level + board-type(catholic) + notable programs.
export function schoolBadges(s: ColorInput): { code: string; label: string; color: string }[] {
  const out: { code: string; label: string; color: string }[] = []
  if (s.type === 'secondary') out.push({ code: 'secondary', label: 'Secondary', color: TYPE_COLORS.secondary })
  else if (s.type === 'elementary') out.push({ code: 'elementary', label: 'Elementary', color: TYPE_COLORS.elementary })
  if (s.board_type === 'catholic') out.push({ code: 'catholic', label: 'Catholic', color: TYPE_COLORS.catholic })
  if (hasProgram(s.programs, 'french')) out.push({ code: 'french', label: 'French Imm.', color: TYPE_COLORS.french })
  if (hasProgram(s.programs, 'gifted') || hasProgram(s.programs, 'pace'))
    out.push({ code: 'gifted', label: 'Gifted/PACE', color: TYPE_COLORS.gifted })
  return out
}

export function programLabel(code: string): string {
  return code.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
