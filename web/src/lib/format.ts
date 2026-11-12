import type { DriftStatus } from '../api/client'

export function percent(ratio: number | null | undefined, digits = 0): string {
  return ratio === null || ratio === undefined ? '–' : `${(ratio * 100).toFixed(digits)}%`
}

export function signedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '–'
  return `${value > 0 ? '+' : ''}${value.toFixed(0)}%`
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '–'
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-CA', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

export function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

export function daysBefore(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() - days)
  return isoDate(date)
}

export const MAX_PERIOD_DAYS = 366
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** Why a period cannot be queried yet, or null. Date inputs emit odd dates while a year is typed. */
export function periodProblem(from: string, to: string): string | null {
  if (!ISO_DATE.test(from) || !ISO_DATE.test(to)) return 'Pick a start and end date.'
  if (from > to) return 'The start date must be before the end date.'
  const days = (Date.parse(to) - Date.parse(from)) / 86_400_000 + 1
  if (days > MAX_PERIOD_DAYS) return `Pick a period of at most ${MAX_PERIOD_DAYS} days.`
  return null
}

export function itemUrl(template: string, key: string): string {
  return template.replace('{key}', encodeURIComponent(key))
}

export const STATUS_STYLES: Record<DriftStatus, { label: string; badge: string; ring: string }> = {
  on_track: {
    label: 'On track',
    badge: 'bg-emerald-100 text-emerald-800',
    ring: 'ring-emerald-200',
  },
  at_risk: { label: 'At risk', badge: 'bg-amber-100 text-amber-800', ring: 'ring-amber-200' },
  off_track: { label: 'Off track', badge: 'bg-rose-100 text-rose-800', ring: 'ring-rose-200' },
  insufficient_data: {
    label: 'Not enough data',
    badge: 'bg-slate-100 text-slate-700',
    ring: 'ring-slate-200',
  },
}

/** Which dashboard section an evidence metric (e.g. "scope.added") belongs to. */
export function sectionOf(metric: string): string {
  return metric.split('.', 1)[0]
}
