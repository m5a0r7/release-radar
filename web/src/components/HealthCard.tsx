import type { DriftReport } from '../api/client'
import { percent, shortDate, STATUS_STYLES } from '../lib/format'
import { Card } from './ui'

export function HealthCard({ report, highlighted }: { report: DriftReport; highlighted: boolean }) {
  const { forecast, progress } = report
  const status = STATUS_STYLES[report.status]

  return (
    <Card id="section-forecast" highlighted={highlighted}>
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Release {report.release.name}
          </p>
          <span
            className={`mt-2 inline-block rounded-full px-3 py-1 text-sm font-semibold ${status.badge}`}
          >
            {status.label}
          </span>
          <p className="mt-3 text-sm text-slate-500">
            {progress.done_at_end} of {progress.done_at_end + progress.open_at_end} tickets done (
            {progress.percent_complete ?? 0}%)
          </p>
        </div>
        <dl className="grid grid-cols-3 gap-6 text-sm">
          <Stat label="Likely finish (P50)" value={shortDate(forecast.p50_date)} />
          <Stat label="Safe estimate (P85)" value={shortDate(forecast.p85_date)} />
          <Stat
            label={
              forecast.target_date ? `On time by ${shortDate(forecast.target_date)}` : 'Target date'
            }
            value={forecast.target_date ? percent(forecast.on_time_probability) : 'Not set'}
          />
        </dl>
      </div>
      <div className="mt-5 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-indigo-500"
          style={{ width: `${progress.percent_complete ?? 0}%` }}
        />
      </div>
    </Card>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 text-xl font-semibold text-slate-900">{value}</dd>
    </div>
  )
}
