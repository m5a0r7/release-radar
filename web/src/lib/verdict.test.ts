import { describe, expect, it } from 'vitest'

import type { DriftReport } from '../api/client'
import { detail, headline } from './verdict'

function report(overrides: {
  status?: DriftReport['status']
  released?: boolean
  forecast?: Partial<DriftReport['forecast']>
  change_pct?: number | null
}): DriftReport {
  return {
    status: overrides.status ?? 'at_risk',
    release: { name: '4.5.0', released: overrides.released ?? false },
    forecast: {
      p50_date: '2026-12-16',
      p85_date: '2026-12-19',
      target_date: '2026-12-15',
      on_time_probability: 0.37,
      ...overrides.forecast,
    },
    progress: { done_at_end: 193, open_at_end: 73 },
    scope: { change_pct: overrides.change_pct ?? 116 },
  } as unknown as DriftReport
}

describe('verdict', () => {
  it('leads with the on-time probability when there is a target', () => {
    expect(headline(report({}))).toBe('37% chance 4.5.0 ships by Dec 15')
    expect(detail(report({}))).toBe(
      'Likely Dec 16, safe estimate Dec 19. 193 of 266 tickets done. Scope grew 116% during the period.',
    )
  })

  it('falls back to the likely date without a target', () => {
    const noTarget = report({ forecast: { target_date: null, on_time_probability: null } })
    expect(headline(noTarget)).toBe('4.5.0 will likely ship Dec 16')
  })

  it('does not forecast without enough history, or after release', () => {
    expect(headline(report({ status: 'insufficient_data' }))).toBe(
      'Not enough history to forecast 4.5.0 yet',
    )
    expect(headline(report({ released: true }))).toBe('4.5.0 has been released')
  })

  it('only mentions scope growth when it is material', () => {
    expect(detail(report({ change_pct: 5 }))).not.toMatch(/Scope grew/)
  })
})
