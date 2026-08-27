const normalizeDigits = (digits: number) => Math.max(0, Math.trunc(digits))

const roundDecimal = (value: number, digits: number) => {
  if (!Number.isFinite(value)) return value
  const safeDigits = normalizeDigits(digits)
  const factor = 10 ** safeDigits
  // Round the absolute value first so decimal halves are handled consistently
  // for both positive and negative values despite IEEE-754 representation noise.
  const roundedAbs = Math.round((Math.abs(value) + Number.EPSILON) * factor) / factor
  return Math.sign(value) * roundedAbs
}

const fixed = (value: number, digits: number) => roundDecimal(value, digits).toFixed(normalizeDigits(digits))

export const formatNumber = (value: unknown, digits = 2) =>
  value == null || !Number.isFinite(Number(value)) ? '—' : fixed(Number(value), digits)

export const formatPercent = (value: unknown, digits = 2) =>
  value == null || !Number.isFinite(Number(value)) ? '—' : `${fixed(Number(value), digits)}%`

export const formatSigned = (value: unknown, digits = 2, suffix = '') => {
  if (value == null || !Number.isFinite(Number(value))) return '—'
  const rounded = roundDecimal(Number(value), digits)
  return `${rounded > 0 ? '+' : ''}${rounded.toFixed(normalizeDigits(digits))}${suffix}`
}

export const formatMoneyYi = (value: unknown, digits = 2) =>
  value == null || !Number.isFinite(Number(value)) ? '—' : `${fixed(Number(value), digits)} 亿`
