import type { ReactNode } from 'react'

import type { DriftReport } from '../api/client'
import { percent, signedPercent } from '../lib/format'
import { ItemLinks } from './ItemLinks'

type Props = { report: DriftReport; itemUrlTemplate: string; highlighted: string | null }

export function MetricsGrid({ report, itemUrlTemplate, highlighted }: Props) {
  const { scope, progress, planning, idle, code } = report
  const delta = progress.completed_in_period - progress.completed_previous_period

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <Tile
        section="scope"
        highlighted={highlighted}
        label="Scope change"
        value={signedPercent(scope.change_pct)}
        caption={`${scope.at_start} → ${scope.at_end} tickets · ${scope.added} added, ${scope.removed} removed`}
      >
        <ItemLinks keys={scope.added_keys} template={itemUrlTemplate} />
      </Tile>
      <Tile
        section="progress"
        highlighted={highlighted}
        label="Completed in period"
        value={String(progress.completed_in_period)}
        caption={`${delta >= 0 ? '+' : ''}${delta} vs previous period (${progress.completed_previous_period})`}
      />
      <Tile
        section="planning"
        highlighted={highlighted}
        label="Unplanned work"
        value={percent(planning.unplanned_share)}
        caption={`${planning.tagged_at_resolution} of ${planning.completed_in_period} completed tickets joined the release within ${planning.window_hours}h of being resolved`}
      >
        <ItemLinks keys={planning.sample_keys} template={itemUrlTemplate} />
      </Tile>
      <Tile
        section="idle"
        highlighted={highlighted}
        label="Idle tickets"
        value={String(idle.idle_items)}
        caption={`${percent(idle.idle_share)} of ${idle.open_items} open tickets had no activity for ${idle.threshold_days}+ days`}
      >
        <ItemLinks keys={idle.idle_keys} template={itemUrlTemplate} />
      </Tile>
      {code.available && (
        <>
          <Tile
            section="code"
            highlighted={highlighted}
            label="Done in code, open in Jira"
            value={String(code.open_items_with_merged_change)}
            caption="Open tickets whose pull request is already merged"
          >
            <ItemLinks keys={code.sample_keys} template={itemUrlTemplate} />
          </Tile>
          <Tile
            section="code"
            highlighted={highlighted}
            label="PRs without a ticket"
            value={percent(code.unlinked_share)}
            caption={`${code.unlinked_merged_in_period} of ${code.project_merged_in_period} merged PRs reference no ticket`}
          />
        </>
      )}
    </div>
  )
}

function Tile({
  section,
  highlighted,
  label,
  value,
  caption,
  children,
}: {
  section: string
  highlighted: string | null
  label: string
  value: string
  caption: string
  children?: ReactNode
}) {
  const active = highlighted === section
  return (
    <div
      data-section={section}
      className={`rounded-xl bg-white p-4 shadow-sm ring-1 transition-shadow ${
        active ? 'ring-2 ring-indigo-400 shadow-md' : 'ring-slate-200'
      }`}
    >
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{caption}</p>
      {children}
    </div>
  )
}
