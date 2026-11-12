import { describe, expect, it } from 'vitest'

import { daysBefore, itemUrl, percent, sectionOf, signedPercent } from './format'

describe('format', () => {
  it('formats ratios and missing values', () => {
    expect(percent(0.8595)).toBe('86%')
    expect(percent(null)).toBe('–')
    expect(signedPercent(116.3)).toBe('+116%')
    expect(signedPercent(-4)).toBe('-4%')
  })

  it('does date arithmetic in UTC', () => {
    expect(daysBefore('2026-03-01', 1)).toBe('2026-02-28')
  })

  it('builds item links safely', () => {
    expect(itemUrl('https://jira.test/browse/{key}', 'KAFKA-1')).toBe(
      'https://jira.test/browse/KAFKA-1',
    )
    expect(itemUrl('https://jira.test/browse/{key}', 'a/../b')).toBe(
      'https://jira.test/browse/a%2F..%2Fb',
    )
  })

  it('maps evidence metrics to dashboard sections', () => {
    expect(sectionOf('planning.unplanned_share')).toBe('planning')
    expect(sectionOf('throughput.week_2026-03-02')).toBe('throughput')
  })
})
