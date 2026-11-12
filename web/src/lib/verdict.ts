import type { DriftReport } from '../api/client'
import { percent, shortDate } from './format'

/** The one-sentence answer: will this release ship on time? */
export function headline(report: DriftReport): string {
  const { release, forecast, status } = report
  if (release.released) return `${release.name} has been released`
  if (status === 'insufficient_data' || !forecast.p50_date)
    return `Not enough history to forecast ${release.name} yet`
  if (forecast.target_date && forecast.on_time_probability !== null)
    return `${percent(forecast.on_time_probability)} chance ${release.name} ships by ${shortDate(forecast.target_date)}`
  return `${release.name} will likely ship ${shortDate(forecast.p50_date)}`
}

export function detail(report: DriftReport): string {
  const { forecast, progress, scope } = report
  const total = progress.done_at_end + progress.open_at_end
  const parts: string[] = []
  if (forecast.p50_date && forecast.p85_date)
    parts.push(
      `Likely ${shortDate(forecast.p50_date)}, safe estimate ${shortDate(forecast.p85_date)}.`,
    )
  parts.push(`${progress.done_at_end} of ${total} tickets done.`)
  if (scope.change_pct !== null && scope.change_pct >= 20)
    parts.push(`Scope grew ${scope.change_pct.toFixed(0)}% during the period.`)
  return parts.join(' ')
}
