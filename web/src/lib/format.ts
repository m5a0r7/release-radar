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
