import { useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import type { TrackedRelease } from '../../api/client'
import { isActive, useCancelSync, useJob, useStartSync } from '../../api/hooks'
import { count, relativeTime } from '../../lib/format'
import { Button } from '../ui'

const ACTIVE = new Set(['queued', 'running'])

/** Sync button plus a live status line; follows syncs started elsewhere, such as the wizard. */
export function SyncControl({
  slug,
  release,
  tracked,
  initialJobId,
}: {
  slug: string
  release: string
  tracked: TrackedRelease | undefined
  initialJobId?: number
}) {
  const [jobId, setJobId] = useState(initialJobId)
  const start = useStartSync()
  const cancel = useCancelSync()
  const backgroundSync = tracked !== undefined && ACTIVE.has(tracked.sync_status)
  const job = useJob(jobId ?? (backgroundSync ? (tracked?.sync_job_id ?? undefined) : undefined))
  const client = useQueryClient()
  const running = start.isPending || isActive(job.data) || backgroundSync

  // A scheduled sync finished: the data behind the dashboard changed.
  const wasBackground = useRef(backgroundSync)
  useEffect(() => {
    if (wasBackground.current && !backgroundSync) {
      for (const key of ['drift', 'narrative', 'releases']) {
        client.invalidateQueries({ queryKey: [key] })
      }
    }
    wasBackground.current = backgroundSync
  }, [backgroundSync, client])

  const progress = (job.data?.progress ?? tracked?.sync_progress) as
    { work_items?: number; code_changes?: number } | undefined
  const phase = job.data?.status ?? tracked?.sync_status
  const stopId = job.data?.id ?? jobId ?? tracked?.sync_job_id ?? undefined
  const errorText = job.data?.last_error ?? tracked?.sync_error ?? ''
  const counted =
    progress !== undefined &&
    (progress.work_items !== undefined || progress.code_changes !== undefined)

  let status: string
  if (start.error) status = 'Could not start sync'
  else if (phase === 'cancelled') status = 'Sync stopped'
  else if (phase === 'failed' || job.data?.status === 'failed') status = 'Sync failed'
  else if (phase === 'queued' && /rate limited/i.test(errorText))
    status = 'Waiting on GitHub’s rate limit'
  else if (running && counted)
    status = `Syncing · ${count(progress?.work_items, 'ticket')}, ${count(progress?.code_changes, 'PR')}`
  else if (phase === 'queued') status = 'Queued…'
  else if (running) status = 'Syncing…'
  else if (tracked?.last_synced_at) status = `Synced ${relativeTime(tracked.last_synced_at)}`
  else status = 'Never synced'

  return (
    <>
      <span
        className={
          start.error || job.data?.status === 'failed'
            ? 'text-xs text-rose-600 dark:text-rose-400'
            : 'num text-xs text-zinc-400'
        }
        aria-live="polite"
      >
        {status}
      </span>
      {running && (
        <Button
          variant="secondary"
          disabled={cancel.isPending || stopId === undefined}
          onClick={() => stopId !== undefined && cancel.mutate(stopId)}
        >
          Stop
        </Button>
      )}
      <Button
        variant="secondary"
        disabled={running}
        onClick={() => start.mutate({ slug, release }, { onSuccess: (id) => setJobId(id) })}
      >
        <RefreshCw className={running ? 'size-3.5 animate-spin' : 'size-3.5'} />
        Sync
      </Button>
    </>
  )
}
