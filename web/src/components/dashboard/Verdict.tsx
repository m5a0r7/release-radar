import { Sparkles } from 'lucide-react'
import { useState } from 'react'

import type { DriftReport } from '../../api/client'
import { useSetTargetDate } from '../../api/hooks'
import { cn } from '../../lib/cn'
import { shortDate, STATUS_STYLES } from '../../lib/format'
import { trackerName } from '../../lib/tracker'
import { detail, headline } from '../../lib/verdict'
import { Button, ErrorNotice, Pill } from '../ui'

export function Verdict({
  report,
  slug,
  storedTarget,
  tracker,
  highlighted,
  onExplain,
}: {
  report: DriftReport
  slug: string
  tracker: string
  storedTarget: string | null | undefined
  highlighted: boolean
  onExplain: () => void
}) {
  const status = STATUS_STYLES[report.status]
  const [editing, setEditing] = useState(false)

  return (
    <section
      data-sections="forecast"
      className={cn(
        'flex items-start justify-between gap-6 rounded-lg transition-shadow',
        highlighted &&
          'ring-2 ring-blue-500/30 ring-offset-8 ring-offset-zinc-50 dark:ring-offset-zinc-950',
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <Pill tone={status.tone}>{status.label}</Pill>
          <span className="num">
            {shortDate(report.period.start)} – {shortDate(report.period.end)}
          </span>
          <span aria-hidden>·</span>
          {editing ? (
            <TargetEditor
              slug={slug}
              release={report.release.name}
              value={storedTarget ?? ''}
              tracker={tracker}
              onClose={() => setEditing(false)}
            />
          ) : (
            <button
              type="button"
              className="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-900 dark:decoration-zinc-700 dark:hover:text-zinc-100"
              onClick={() => setEditing(true)}
            >
              {report.release.target_date
                ? `target ${shortDate(report.release.target_date)}${storedTarget ? '' : ` (from ${trackerName(tracker)})`}`
                : 'Set a target date'}
            </button>
          )}
        </div>
        <h1 className="num mt-3 text-2xl font-semibold tracking-tight">{headline(report)}</h1>
        <p className="mt-1 text-sm text-zinc-500">{detail(report)}</p>
      </div>
      <Button variant="accent" onClick={onExplain} className="shrink-0">
        <Sparkles className="size-4" />
        Explain
      </Button>
    </section>
  )
}

function TargetEditor({
  slug,
  release,
  value,
  tracker,
  onClose,
}: {
  slug: string
  release: string
  value: string
  tracker: string
  onClose: () => void
}) {
  const [draft, setDraft] = useState(value)
  const save = useSetTargetDate(slug)
  const submit = (targetDate: string | null) =>
    save.mutate({ release, targetDate }, { onSuccess: onClose })

  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <input
        type="date"
        aria-label="Target date"
        autoFocus
        className="rounded-md border border-zinc-300 bg-white px-2 py-0.5 text-xs dark:border-zinc-700 dark:bg-zinc-900"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      <Button size="sm" disabled={!draft || save.isPending} onClick={() => submit(draft)}>
        Save
      </Button>
      {value && (
        <Button size="sm" variant="ghost" disabled={save.isPending} onClick={() => submit(null)}>
          Use {tracker === 'github' ? 'milestone' : 'Jira'} date
        </Button>
      )}
      <Button size="sm" variant="ghost" onClick={onClose}>
        Cancel
      </Button>
      {save.error && <ErrorNotice error={save.error} />}
    </span>
  )
}
