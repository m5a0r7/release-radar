import { cn } from '../../lib/cn'
import type { PeriodPreset } from '../../lib/format'

const OPTIONS: PeriodPreset[] = ['4w', '8w', '12w', 'custom']

export function PeriodPicker({
  preset,
  from,
  to,
  today,
  onChange,
}: {
  preset: PeriodPreset
  from: string
  to: string
  today: string
  onChange: (patch: { period?: PeriodPreset; from?: string; to?: string }) => void
}) {
  return (
    <div className="flex items-center gap-2">
      {preset === 'custom' && (
        <div className="flex items-center gap-1 text-xs">
          <input
            type="date"
            aria-label="From"
            className="rounded-md border border-zinc-200 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            value={from}
            max={to}
            onChange={(e) => onChange({ from: e.target.value })}
          />
          <span className="text-zinc-400">–</span>
          <input
            type="date"
            aria-label="To"
            className="rounded-md border border-zinc-200 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            value={to}
            min={from}
            max={today}
            onChange={(e) => onChange({ to: e.target.value })}
          />
        </div>
      )}
      <div
        className="flex rounded-md bg-zinc-100 p-0.5 dark:bg-zinc-800/60"
        role="radiogroup"
        aria-label="Period"
      >
        {OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={preset === option}
            onClick={() =>
              onChange(option === 'custom' ? { period: option, from, to } : { period: option })
            }
            className={cn(
              'rounded px-2 py-1 text-xs',
              preset === option
                ? 'bg-white font-medium ring-1 ring-zinc-200 dark:bg-zinc-800 dark:ring-zinc-700'
                : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100',
            )}
          >
            {option === 'custom' ? 'Custom' : option}
          </button>
        ))}
      </div>
    </div>
  )
}
