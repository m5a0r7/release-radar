import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import type { ReactNode } from 'react'

import type { DriftReport } from '../../api/client'
import { cn } from '../../lib/cn'
import { percent, searchUrl, signedPercent } from '../../lib/format'
import { trackerName } from '../../lib/tracker'
import { Card } from '../ui'

type Props = {
  report: DriftReport
  searchTemplate: string
  tracker: string
  highlighted: string | null
}

export function KpiTiles({ report, searchTemplate, tracker, highlighted }: Props) {
  const { scope, planning, idle, progress, burnup, throughput } = report
  const drillLabel = `View in ${trackerName(tracker)} →`
  const resolvedDelta = progress.completed_in_period - progress.completed_previous_period

  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Tile
        sections={['scope']}
        highlighted={highlighted}
        drillLabel={drillLabel}
        label="Scope change"
        value={signedPercent(scope.change_pct)}
        chart={<Sparkline values={burnup.map((p) => p.scope)} />}
        delta={<Delta value={scope.added} unit=" added" upIsBad />}
        foot={`${scope.removed} removed`}
        drill={scope.added_keys.length ? searchUrl(searchTemplate, scope.added_keys) : undefined}
      />
      <Tile
        sections={['planning']}
        highlighted={highlighted}
        drillLabel={drillLabel}
        label="Unplanned work"
        value={percent(planning.unplanned_share)}
        chart={<Meter share={planning.unplanned_share} />}
        foot={`${planning.tagged_at_resolution} of ${planning.completed_in_period} resolved tickets joined within ${planning.window_hours}h of resolution`}
        drill={
          planning.sample_keys.length ? searchUrl(searchTemplate, planning.sample_keys) : undefined
        }
      />
      <Tile
        sections={['idle']}
        highlighted={highlighted}
        drillLabel={drillLabel}
        label="Idle tickets"
        value={String(idle.idle_items)}
        chart={<Meter share={idle.idle_share} />}
        foot={`${percent(idle.idle_share)} of ${idle.open_items} open · quiet ${idle.threshold_days}+ days`}
        drill={idle.idle_keys.length ? searchUrl(searchTemplate, idle.idle_keys) : undefined}
      />
      <Tile
        sections={['progress', 'throughput']}
        highlighted={highlighted}
        drillLabel={drillLabel}
        label="Resolved"
        value={String(progress.completed_in_period)}
        chart={<Sparkline values={throughput.weekly.map((w) => w.completed)} />}
        delta={<Delta value={resolvedDelta} />}
        foot={`vs ${progress.completed_previous_period} previous period`}
      />
    </section>
  )
}

function Tile({
  sections,
  highlighted,
  label,
  value,
  chart,
  delta,
  foot,
  drill,
  drillLabel,
}: {
  sections: string[]
  highlighted: string | null
  label: string
  value: string
  chart: ReactNode
  delta?: ReactNode
  foot: string
  drill?: string
  drillLabel: string
}) {
  return (
    <Card
      data-sections={sections.join(' ')}
      highlighted={highlighted !== null && sections.includes(highlighted)}
      className="flex flex-col p-4"
    >
      <p className="text-xs text-zinc-500">{label}</p>
      <div className="mt-2 flex items-end justify-between gap-3">
        <p className="num text-2xl font-semibold tracking-tight">{value}</p>
        {chart}
      </div>
      <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs">
        {delta}
        <span className="text-zinc-400">{foot}</span>
      </p>
      {drill && (
        <a
          href={drill}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-auto pt-2 text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          {drillLabel}
        </a>
      )}
    </Card>
  )
}

function Delta({
  value,
  unit = '',
  upIsBad = false,
}: {
  value: number
  unit?: string
  upIsBad?: boolean
}) {
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus
  const bad = upIsBad ? value > 0 : value < 0
  return (
    <span
      className={cn(
        'num flex items-center',
        value === 0
          ? 'text-zinc-500'
          : bad
            ? 'text-rose-600 dark:text-rose-400'
            : 'text-emerald-600 dark:text-emerald-400',
      )}
    >
      <Icon className="size-3" aria-hidden />
      {value > 0 ? '+' : ''}
      {value}
      {unit}
    </span>
  )
}

export function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const width = 80
  const height = 24
  const low = Math.min(...values)
  const range = Math.max(...values) - low || 1
  const points = values
    .map(
      (v, i) =>
        `${((i / (values.length - 1)) * width).toFixed(1)},${(height - 1 - ((v - low) / range) * (height - 2)).toFixed(1)}`,
    )
    .join(' ')
  return (
    <svg width={width} height={height} className="shrink-0" aria-hidden>
      <polyline points={points} fill="none" stroke="var(--chart-spark)" strokeWidth="1.5" />
    </svg>
  )
}

function Meter({ share }: { share: number | null }) {
  return (
    <div
      className="mb-1.5 h-1.5 w-20 shrink-0 rounded-full bg-zinc-100 dark:bg-zinc-800"
      aria-hidden
    >
      <div
        className="h-full rounded-full bg-zinc-400 dark:bg-zinc-500"
        style={{ width: `${Math.round((share ?? 0) * 100)}%` }}
      />
    </div>
  )
}
