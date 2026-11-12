import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

export type Project = components['schemas']['ProjectOut']
export type Release = components['schemas']['ReleaseOut']
export type Job = components['schemas']['JobOut']
export type DriftReport = components['schemas']['DriftReport']
export type Narrative = components['schemas']['NarrativeResponse']
export type Evidence = components['schemas']['Evidence']
export type DriftStatus = components['schemas']['DriftStatus']
export type TrackedRelease = components['schemas']['TrackedReleaseOut']
export type Me = components['schemas']['MeOut']
export type TrackerCheck = components['schemas']['TrackerCheckOut']
export type CodeCheck = components['schemas']['CodeCheckOut']
export type Repository = components['schemas']['RepositoryOut']

export const api = createClient<paths>({ baseUrl: '' })

/** An RFC 9457 problem returned by the API. */
export class ApiError extends Error {
  readonly status: number
  readonly problem: Problem

  constructor(status: number, problem: Problem) {
    super(problem.title ?? `Request failed (${status})`)
    this.status = status
    this.problem = problem
  }

  get detail(): string | undefined {
    return this.problem.detail
  }
}

export type Problem = { title?: string; detail?: string; [extension: string]: unknown }

/** Unwrap an openapi-fetch result, turning problem responses into `ApiError`. */
export async function unwrap<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request
  if (error !== undefined || data === undefined) {
    const problem = typeof error === 'object' && error !== null ? (error as Problem) : {}
    throw new ApiError(response.status, problem)
  }
  return data
}
