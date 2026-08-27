import { describe, expect, it } from 'vitest'
import { comparableSnapshots, filterConsensus, periodScope } from './research'

describe('quarterly disclosure comparability', () => {
  it('classifies Q1/Q3 as top10 and Q2/Q4 as full', () => {
    expect(periodScope('2026Q1')).toBe('top10')
    expect(periodScope('2026Q2')).toBe('full')
    expect(periodScope('2026Q3')).toBe('top10')
    expect(periodScope('2026Q4')).toBe('full')
  })

  it('uses top10 on both sides when disclosure scope differs', () => {
    const previous = Array.from({ length: 15 }, (_, i) => ({ quarter: '2026Q2', stock_code: String(i), weight_pct: 15 - i }))
    const current = Array.from({ length: 15 }, (_, i) => ({ quarter: '2026Q3', stock_code: String(i), weight_pct: 15 - i }))
    const result = comparableSnapshots(previous, current, '2026Q2', '2026Q3')
    expect(result.oldRows).toHaveLength(10)
    expect(result.newRows).toHaveLength(10)
    expect(result.basis).toBe('top10_comparable')
  })
})

describe('consensus filters', () => {
  const rows = [
    { consensus_level: '高', consensus_trend: '增强' },
    { consensus_level: '高', consensus_trend: '弱化' },
    { consensus_level: '低', consensus_trend: '增强' },
  ]
  it('filters level and trend independently', () => {
    expect(filterConsensus(rows, '高', '全部')).toHaveLength(2)
    expect(filterConsensus(rows, '全部', '增强')).toHaveLength(2)
    expect(filterConsensus(rows, '高', '增强')).toHaveLength(1)
  })
})
