import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { DriftReport } from '../api/client'
import { shortDate } from '../lib/format'
import { Card } from './ui'

export function ThroughputChart({
  report,
  highlighted,
}: {
  report: DriftReport
  highlighted: boolean
}) {
  const weeks = report.throughput.weekly.map((week) => ({
    label: shortDate(week.start),
    completed: week.completed,
    anomaly: week.anomaly,
    partial: !week.full_week,
  }))
  const mean = report.throughput.mean_per_full_week

  return (
    <Card
      id="section-throughput"
      title="Tickets resolved per week"
      highlighted={highlighted}
      action={
        <span className="flex items-center gap-3 text-xs text-slate-500">
          <Legend className="bg-indigo-500" label="Normal" />
          <Legend className="bg-rose-500" label="Unusual week" />
          <Legend className="bg-slate-300" label="Partial week" />
        </span>
      }
    >
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={weeks} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid vertical={false} stroke="#e2e8f0" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 12, fill: '#64748b' }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 12, fill: '#64748b' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip cursor={{ fill: '#f1f5f9' }} formatter={(value) => [value, 'Resolved']} />
            {mean !== null && mean !== undefined && (
              <ReferenceLine
                y={mean}
                stroke="#94a3b8"
                strokeDasharray="4 4"
                label={{ value: 'avg', fill: '#94a3b8', fontSize: 11, position: 'right' }}
              />
            )}
            <Bar dataKey="completed" radius={[4, 4, 0, 0]}>
              {weeks.map((week) => (
                <Cell
                  key={week.label}
                  fill={week.anomaly ? '#f43f5e' : week.partial ? '#cbd5e1' : '#6366f1'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`size-2.5 rounded-sm ${className}`} />
      {label}
    </span>
  )
}
