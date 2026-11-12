import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Job } from './client'

export type Period = { from: string; to: string; targetDate?: string }

const ACTIVE_JOB = new Set(['queued', 'running'])

function periodQuery(period: Period) {
  return {
    from: period.from,
    to: period.to,
    ...(period.targetDate ? { target_date: period.targetDate } : {}),
  }
}

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: () => unwrap(api.GET('/v1/projects')),
  })
}

export function useCreateProject() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { slug: string; tracker_key: string; repository?: string }) =>
      unwrap(api.POST('/v1/projects', { body: { tracker: 'jira', code_host: 'github', ...body } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ['projects'] }),
  })
}

export function useReleases(slug: string | undefined) {
  return useQuery({
    queryKey: ['releases', slug],
    enabled: slug !== undefined,
    queryFn: () =>
      unwrap(
        api.GET('/v1/projects/{slug}/releases', {
          params: { path: { slug: slug! }, query: { limit: 100 } },
        }),
      ),
  })
}

export function useDrift(slug: string | undefined, release: string | undefined, period: Period) {
  return useQuery({
    queryKey: ['drift', slug, release, period],
    enabled: slug !== undefined && release !== undefined,
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET('/v1/projects/{slug}/releases/{release}/drift', {
          params: { path: { slug: slug!, release: release! }, query: periodQuery(period) },
        }),
      ),
  })
}

export function useNarrative(
  slug: string | undefined,
  release: string | undefined,
  period: Period,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['narrative', slug, release, period],
    enabled: enabled && slug !== undefined && release !== undefined,
    staleTime: Infinity,
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET('/v1/projects/{slug}/releases/{release}/narrative', {
          params: { path: { slug: slug!, release: release! }, query: periodQuery(period) },
        }),
      ),
  })
}

export function useStartSync(slug: string | undefined, release: string | undefined) {
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/v1/projects/{slug}/releases/{release}/syncs', {
          params: { path: { slug: slug!, release: release! } },
        }),
      ),
  })
}

/** Polls a job until it finishes, then refreshes everything derived from synced data. */
export function useJob(jobId: number | undefined) {
  const client = useQueryClient()
  return useQuery({
    queryKey: ['job', jobId],
    enabled: jobId !== undefined,
    refetchInterval: (query) => (isActive(query.state.data) ? 1500 : false),
    queryFn: async () => {
      const job = await unwrap(
        api.GET('/v1/jobs/{job_id}', { params: { path: { job_id: jobId! } } }),
      )
      if (!isActive(job)) {
        await Promise.all([
          client.invalidateQueries({ queryKey: ['drift'] }),
          client.invalidateQueries({ queryKey: ['narrative'] }),
          client.invalidateQueries({ queryKey: ['releases'] }),
        ])
      }
      return job
    },
  })
}

export function isActive(job: Job | undefined): boolean {
  return job !== undefined && ACTIVE_JOB.has(job.status)
}
