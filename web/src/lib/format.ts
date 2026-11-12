import type { DriftStatus } from '../api/client'
import type { Tone } from '../components/ui'

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

/** A tracker search listing these items, e.g. a Jira JQL `key in (...)` query. */
export function searchUrl(template: string, keys: string[]): string {
  return template.replace('{keys}', encodeURIComponent(keys.join(',')))
}

export const STATUS_STYLES: Record<DriftStatus, { label: string; tone: Tone; dot: string }> = {
  on_track: { label: 'On track', tone: 'emerald', dot: 'bg-emerald-500' },
  at_risk: { label: 'At risk', tone: 'amber', dot: 'bg-amber-500' },
  off_track: { label: 'Off track', tone: 'rose', dot: 'bg-rose-500' },
  insufficient_data: {
    label: 'Not enough data',
    tone: 'zinc',
    dot: 'bg-zinc-300 dark:bg-zinc-600',
  },
}

const STATUS_RANK: DriftStatus[] = ['off_track', 'at_risk', 'on_track', 'insufficient_data']

/** The most worrying of several release statuses. */
export function worstStatus(statuses: DriftStatus[]): DriftStatus | undefined {
  return STATUS_RANK.find((status) => statuses.includes(status))
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'never'
  const minutes = Math.round((now - Date.parse(iso)) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return `${days} d ago`
}

export function count(n: number | null | undefined, noun: string): string {
  const value = n ?? 0
  return `${value} ${noun}${value === 1 ? '' : 's'}`
}

export const PERIOD_PRESETS = { '4w': 28, '8w': 56, '12w': 84 } as const
export type PeriodPreset = keyof typeof PERIOD_PRESETS | 'custom'

/** The inclusive date range a preset covers, ending today. */
export function presetRange(preset: keyof typeof PERIOD_PRESETS, today: string) {
  return { from: daysBefore(today, PERIOD_PRESETS[preset] - 1), to: today }
}

/** Which dashboard section an evidence metric (e.g. "scope.added") belongs to. */
export function sectionOf(metric: string): string {
  return metric.split('.', 1)[0]
}
