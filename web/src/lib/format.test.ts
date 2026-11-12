import { describe, expect, it } from 'vitest'

import {
  daysBefore,
  itemUrl,
  percent,
  periodProblem,
  presetRange,
  relativeTime,
  sectionOf,
  signedPercent,
  worstStatus,
} from './format'

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

  it('rejects periods the API would refuse, such as half-typed years', () => {
    expect(periodProblem('2026-09-18', '2026-11-12')).toBeNull()
    expect(periodProblem('1520-09-10', '2026-11-12')).toMatch(/at most 366 days/)
    expect(periodProblem('5202-09-10', '2026-11-12')).toMatch(/before the end/)
    expect(periodProblem('', '2026-11-12')).toMatch(/Pick a start/)
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

  it('summarises a project by its most worrying release', () => {
    expect(worstStatus(['on_track', 'at_risk', 'insufficient_data'])).toBe('at_risk')
    expect(worstStatus([])).toBeUndefined()
  })

  it('describes sync times relative to now', () => {
    const now = Date.parse('2026-11-12T12:00:00Z')
    expect(relativeTime('2026-11-12T11:58:00Z', now)).toBe('2 min ago')
    expect(relativeTime('2026-11-12T09:00:00Z', now)).toBe('3 h ago')
    expect(relativeTime(null, now)).toBe('never')
  })

  it('turns period presets into inclusive ranges ending today', () => {
    expect(presetRange('4w', '2026-11-12')).toEqual({ from: '2026-10-16', to: '2026-11-12' })
  })
})
