import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DriftReport } from '../../api/client'
import { shortDate } from '../../lib/format'
import { trackerLabel } from '../../lib/tracker'
import { Card, CardTitle } from '../ui'

const DAY_MS = 86_400_000
const toTime = (iso: string) => Date.parse(`${iso}T00:00:00Z`)
const label = (time: number) => shortDate(new Date(time).toISOString().slice(0, 10))
const axisTick = { fontSize: 11, fill: 'var(--chart-axis)' }

/** Tickets done against release scope, week by week, with the median forecast to completion. */
export function BurnupChart({
  report,
  trackerKey,
  tracker,
  highlighted,
}: {
  report: DriftReport
  trackerKey: string
  tracker: string
  highlighted: boolean
}) {
  const points = report.burnup.map((p) => ({ t: toTime(p.at), scope: p.scope, done: p.done }))
  const last = points.at(-1)
  const { p50_date: p50, target_date: target } = report.forecast
  const forecast =
    last && p50 && !report.release.released && last.done < last.scope
      ? [
          { t: last.t, forecast: last.done },
          { t: toTime(p50), forecast: last.scope },
        ]
      : []
  const end = Math.max(last?.t ?? 0, ...forecast.map((p) => p.t), target ? toTime(target) : 0)

  return (
    <Card data-sections="throughput" highlighted={highlighted} className="p-5 xl:col-span-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>Burn-up: tickets done vs. release scope</CardTitle>
        <div className="flex gap-3 text-xs text-zinc-500">
          <Legend className="border-t-2 border-blue-600 dark:border-blue-500" label="Done" />
          <Legend className="border-t-2 border-dashed border-zinc-400" label="Scope" />
          {forecast.length > 0 && (
            <Legend className="border-t-2 border-dotted border-blue-400" label="Forecast" />
          )}
        </div>
      </div>
      <p className="mt-0.5 text-xs text-zinc-400">
        Tickets, weekly · source: {trackerLabel(tracker, trackerKey)}
      </p>
      {points.length < 2 ? (
        <p className="mt-6 text-sm text-zinc-500">Not enough history in this period.</p>
      ) : (
        <div className="mt-3 h-60">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart margin={{ top: 16, right: 12, bottom: 0, left: -20 }}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={[points[0].t, end + DAY_MS]}
                tickFormatter={label}
                tick={axisTick}
                tickLine={false}
                axisLine={false}
                allowDuplicatedCategory={false}
              />
              <YAxis allowDecimals={false} tick={axisTick} tickLine={false} axisLine={false} />
              <Tooltip
                labelFormatter={(value) => label(Number(value))}
                contentStyle={{ fontSize: 12, borderRadius: 6 }}
              />
              <Line
                data={points}
                dataKey="scope"
                name="Scope"
                stroke="var(--chart-scope)"
                strokeWidth={2}
                strokeDasharray="4 3"
                dot={false}
                isAnimationActive={false}
              />
              <Line
                data={points}
                dataKey="done"
                name="Done"
                stroke="var(--chart-done)"
                strokeWidth={2.5}
                dot={false}
                isAnimationActive={false}
              />
              {forecast.length > 0 && (
                <Line
                  data={forecast}
                  dataKey="forecast"
                  name="Forecast (median)"
                  stroke="var(--chart-forecast)"
                  strokeWidth={2}
                  strokeDasharray="2 3"
                  dot={false}
                  isAnimationActive={false}
                />
              )}
              {target && (
                <ReferenceLine
                  x={toTime(target)}
                  stroke="var(--chart-target)"
                  strokeDasharray="3 3"
                  label={{
                    value: `Target ${shortDate(target)}`,
                    position: 'insideTopRight',
                    fill: 'var(--chart-target)',
                    fontSize: 10,
                  }}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-3 ${className}`} />
      {label}
    </span>
  )
}
