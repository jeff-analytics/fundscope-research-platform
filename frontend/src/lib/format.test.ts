import { describe, expect, it } from 'vitest'
import { formatMoneyYi, formatNumber, formatPercent, formatSigned } from './format'

describe('research number formatting', () => {
  it('defaults analytical values to two decimals', () => {
    expect(formatNumber(12.345)).toBe('12.35')
    expect(formatPercent(8.126)).toBe('8.13%')
    expect(formatSigned(1.236, 2, ' pp')).toBe('+1.24 pp')
    expect(formatMoneyYi(126.345)).toBe('126.35 亿')
  })

  it('rounds decimal-half boundaries consistently for financial display', () => {
    expect(formatNumber(126.345)).toBe('126.35')
    expect(formatNumber(-126.345)).toBe('-126.35')
    expect(formatPercent(1.005)).toBe('1.01%')
    expect(formatSigned(-1.235, 2, ' pp')).toBe('-1.24 pp')
    expect(formatMoneyYi(-126.345)).toBe('-126.35 亿')
  })

  it('keeps zero unsigned and rejects non-finite values', () => {
    expect(formatSigned(0, 2, ' pp')).toBe('0.00 pp')
    expect(formatNumber(null)).toBe('—')
    expect(formatPercent(Number.NaN)).toBe('—')
  })
})
