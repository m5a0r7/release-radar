import type { Release } from '../api/client'

export function releasePath(slug: string, release: string): string {
  return `/p/${encodeURIComponent(slug)}/${encodeURIComponent(release)}`
}

/** The upcoming release with the highest version, else the newest one. */
export function defaultRelease(releases: Pick<Release, 'name' | 'released'>[]): string | undefined {
  const upcoming = releases.filter((r) => !r.released)
  const pool = upcoming.length ? upcoming : releases
  return [...pool].sort((a, b) => b.name.localeCompare(a.name, undefined, { numeric: true }))[0]
    ?.name
}
