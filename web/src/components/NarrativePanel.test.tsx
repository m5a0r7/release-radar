import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Narrative } from '../api/client'
import { NarrativePanel } from './NarrativePanel'

const narrative: Narrative = {
  project: 'kafka',
  release: '4.5.0',
  period: { start: '2026-09-18', end: '2026-11-12', days: 56 },
  status: 'at_risk',
  summary: 'Most completed work was never planned.',
  findings: [
    {
      claim: '86% of completed tickets were unplanned.',
      hypothesis: 'Tickets are tagged to the release when they are resolved.',
      confidence: 0.6,
      model_confidence: 0.8,
      evidence: [
        {
          id: 'E11',
          metric: 'planning.unplanned_share',
          value: 86,
          unit: '%',
          description: 'Unplanned share',
          keys: [],
        },
      ],
    },
  ],
  recommendation: null,
  caveats: ['Small sample.'],
  meta: {
    provider: 'anthropic',
    model: 'claude-sonnet-5-5',
    prompt_version: 'drift-v1',
    generated_at: '2026-11-12T00:00:00Z',
    cached: false,
    degraded: false,
    confidence_cap: 0.6,
    verification_errors: [],
  },
}

describe('NarrativePanel', () => {
  it('shows calibrated confidence and links evidence back to the dashboard', () => {
    const onEvidence = vi.fn()
    render(
      <NarrativePanel
        narrative={narrative}
        loading={false}
        error={null}
        requested
        onExplain={() => {}}
        onEvidence={onEvidence}
        itemUrlTemplate="https://jira.test/browse/{key}"
        searchUrlTemplate="https://jira.test/issues/?jql=key%20in%20({keys})"
        tracker="jira"
      />,
    )

    expect(screen.getByText(/60% conf/)).toBeInTheDocument()
    expect(screen.getByText('(capped)')).toBeInTheDocument()
    expect(screen.getByText(/Likely cause/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /E11/ }))
    expect(onEvidence).toHaveBeenCalledWith('planning')
  })

  it('offers to explain before a narrative is requested', () => {
    const onExplain = vi.fn()
    render(
      <NarrativePanel
        narrative={undefined}
        loading={false}
        error={null}
        requested={false}
        onExplain={onExplain}
        onEvidence={() => {}}
        itemUrlTemplate=""
        searchUrlTemplate=""
        tracker="jira"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Explain with AI' }))
    expect(onExplain).toHaveBeenCalled()
  })
})
