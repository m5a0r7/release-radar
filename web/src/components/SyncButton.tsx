import { useState } from 'react'

import { ApiError } from '../api/client'
import { isActive, useJob, useStartSync } from '../api/hooks'
import { Button } from './ui'

export function SyncButton({ slug, release }: { slug: string; release: string }) {
  const [jobId, setJobId] = useState<number>()
  const start = useStartSync(slug, release)
  const job = useJob(jobId)
  const running = start.isPending || isActive(job.data)

  function sync() {
    start.mutate(undefined, {
      onSuccess: (created) => setJobId(created.id),
      onError: (error) => {
        // A sync is already running: follow that job instead of failing.
        if (error instanceof ApiError && typeof error.problem.job_id === 'number') {
          setJobId(error.problem.job_id)
        }
      },
    })
  }

  const progress = job.data?.progress as
    { stage?: string; work_items?: number; code_changes?: number } | undefined

  return (
    <div className="flex items-center gap-3">
      <Button onClick={sync} disabled={running}>
        {running ? 'Syncing…' : 'Sync now'}
      </Button>
      <span className="text-xs text-slate-500" aria-live="polite">
        {running && progress?.stage && (
          <>
            {count(progress.work_items, 'ticket')} · {count(progress.code_changes, 'PR')}
          </>
        )}
        {job.data?.status === 'succeeded' &&
          `Synced · ${count(progress?.work_items, 'ticket')}, ${count(progress?.code_changes, 'PR')} updated`}
        {job.data?.status === 'failed' && <span className="text-rose-700">Sync failed</span>}
        {start.error && !(start.error instanceof ApiError && start.error.status === 409) && (
          <span className="text-rose-700">Could not start sync</span>
        )}
      </span>
    </div>
  )
}

function count(n: number | undefined, noun: string): string {
  const value = n ?? 0
  return `${value} ${noun}${value === 1 ? '' : 's'}`
}
