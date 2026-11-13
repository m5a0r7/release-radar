import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useState } from 'react'

import { isoDate, presetRange } from '../lib/format'
import type { TrackerKind } from '../lib/tracker'
import { api, ApiError, unwrap, type Job, type Me, type Problem } from './client'

export type Period = { from: string; to: string }

const ACTIVE_JOB = new Set(['queued', 'running'])

export function useAuthConfig() {
  return useQuery({
    queryKey: ['auth-config'],
    staleTime: Infinity,
    queryFn: () => unwrap(api.GET('/v1/auth/config')),
  })
}

/** The signed-in user, or null when signed out. */
export function useMe() {
  return useQuery({
    queryKey: ['me'],
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await unwrap(api.GET('/v1/me'))
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
  })
}

export function useDemoSignIn() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/v1/auth/demo')),
    onSuccess: (me) => {
      client.clear()
      client.setQueryData(['me'], me)
    },
  })
}

export function useSignOut() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api.POST('/v1/auth/logout')
    },
    onSuccess: () => {
      client.clear()
      client.setQueryData(['me'], null)
    },
  })
}

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: () => unwrap(api.GET('/v1/projects')),
    // Keeps "Syncing" and "Synced N min ago" current while a background sync runs.
    refetchInterval: (query) =>
      query.state.data?.some((p) => p.tracked_releases.some((r) => ACTIVE_JOB.has(r.sync_status)))
        ? 3000
        : 60_000,
  })
}

export function useCreateProject() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      slug: string
      tracker: TrackerKind
      tracker_key: string
      repository?: string
    }) => unwrap(api.POST('/v1/projects', { body: { code_host: 'github', ...body } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ['projects'] }),
  })
}

export function useDeleteProject() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (slug: string) => {
      const { error, response } = await api.DELETE('/v1/projects/{slug}', {
        params: { path: { slug } },
      })
      if (error !== undefined) throw new ApiError(response.status, error as Problem)
    },
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

export function useSetTargetDate(slug: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ release, targetDate }: { release: string; targetDate: string | null }) =>
      unwrap(
        api.PATCH('/v1/projects/{slug}/releases/{release}', {
          params: { path: { slug, release } },
          body: { target_date: targetDate },
        }),
      ),
    onSuccess: () =>
      Promise.all(
        ['drift', 'narrative', 'releases', 'projects'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}

function driftQuery(slug: string, release: string, period: Period) {
  return {
    queryKey: ['drift', slug, release, period],
    queryFn: () =>
      unwrap(
        api.GET('/v1/projects/{slug}/releases/{release}/drift', {
          params: { path: { slug, release }, query: period },
        }),
      ),
  }
}

export function useDrift(
  slug: string | undefined,
  release: string | undefined,
  period: Period,
  enabled: boolean,
) {
  return useQuery({
    ...driftQuery(slug ?? '', release ?? '', period),
    enabled: enabled && slug !== undefined && release !== undefined,
    placeholderData: keepPreviousData,
  })
}

/** Default-period drift statuses, shared with the dashboard's default view through the cache. */
export function useReleaseStatuses(releases: { slug: string; release: string }[]) {
  const [today] = useState(() => isoDate(new Date()))
  const period = presetRange('8w', today)
  return useQueries({
    queries: releases.map(({ slug, release }) => ({
      ...driftQuery(slug, release, period),
      staleTime: 5 * 60_000,
      select: (report: { status: string }) => report.status,
    })),
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
          params: { path: { slug: slug!, release: release! }, query: period },
        }),
      ),
  })
}

/** Starts a sync, or returns the job already running for that release. */
export async function startSync(slug: string, release: string): Promise<number> {
  try {
    const job = await unwrap(
      api.POST('/v1/projects/{slug}/releases/{release}/syncs', {
        params: { path: { slug, release } },
      }),
    )
    return job.id
  } catch (error) {
    if (error instanceof ApiError && typeof error.problem.job_id === 'number') {
      return error.problem.job_id
    }
    throw error
  }
}

export function useStartSync() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ slug, release }: { slug: string; release: string }) => startSync(slug, release),
    onSuccess: () => client.invalidateQueries({ queryKey: ['projects'] }),
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
        await Promise.all(
          ['drift', 'narrative', 'releases', 'projects'].map((key) =>
            client.invalidateQueries({ queryKey: [key] }),
          ),
        )
      }
      return job
    },
  })
}

export function isActive(job: Job | undefined): boolean {
  return job !== undefined && ACTIVE_JOB.has(job.status)
}

export function useTrackerCheck() {
  return useMutation({
    mutationFn: (body: { tracker: TrackerKind; tracker_key: string }) =>
      unwrap(api.POST('/v1/connect/tracker', { body })),
  })
}

export function useCodeCheck() {
  return useMutation({
    mutationFn: (body: { repository: string; tracker: TrackerKind; tracker_key: string }) =>
      unwrap(api.POST('/v1/connect/code', { body: { code_host: 'github', ...body } })),
  })
}

export function useRepositorySearch(query: string) {
  return useQuery({
    queryKey: ['repositories', query],
    enabled: query.length >= 2,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET('/v1/connect/repositories', { params: { query: { q: query } } })),
  })
}
