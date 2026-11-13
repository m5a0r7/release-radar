import { Plus, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import type { DriftStatus, Project } from '../api/client'
import { startSync, useDeleteProject, useProjects, useReleaseStatuses } from '../api/hooks'
import { Crumb, PageHeader } from '../components/AppShell'
import { buttonClass } from '../components/styles'
import { Button, Card, ErrorNotice, GitHubIcon, Pill, Spinner } from '../components/ui'
import { count, relativeTime, STATUS_STYLES, worstStatus } from '../lib/format'
import { trackerLabel } from '../lib/tracker'
import { useQueryClient } from '@tanstack/react-query'

const ACTIVE = new Set(['queued', 'running'])

export function ProjectsPage() {
  const projects = useProjects()

  return (
    <>
      <PageHeader crumbs={<Crumb>Projects</Crumb>} />
      <main className="flex-1 p-6">
        <div className="mx-auto max-w-5xl">
          <div className="flex items-end justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Projects</h1>
              <p className="mt-1 text-sm text-zinc-500">
                Each project links a Jira project or GitHub repository&rsquo;s issues to the
                repository whose pull requests reference them.
              </p>
            </div>
            <Link to="/projects/new" className={buttonClass('primary')}>
              <Plus className="size-4" />
              Connect project
            </Link>
          </div>

          <div className="mt-6">
            {projects.isPending && <Spinner label="Loading projects…" />}
            {projects.error && <ErrorNotice error={projects.error} />}
            {projects.data?.length === 0 && <EmptyState />}
            {!!projects.data?.length && (
              <Card className="overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900/50">
                    <tr>
                      <th className="px-4 py-2 font-medium">Project</th>
                      <th className="px-4 py-2 font-medium">Repository</th>
                      <th className="px-4 py-2 font-medium">Tracking</th>
                      <th className="px-4 py-2 font-medium">Worst release</th>
                      <th className="px-4 py-2 font-medium">Last sync</th>
                      <th className="px-4 py-2">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {projects.data.map((project) => (
                      <ProjectRow key={project.slug} project={project} />
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
            {!!projects.data?.length && (
              <p className="mt-3 text-xs text-zinc-400">
                Tracked releases re-sync automatically in the background.
              </p>
            )}
          </div>
        </div>
      </main>
    </>
  )
}

function ProjectRow({ project }: { project: Project }) {
  const releases = project.tracked_releases
  const statuses = useReleaseStatuses(
    releases.map((r) => ({ slug: project.slug, release: r.name })),
  )
  const worst = worstStatus(statuses.flatMap((s) => (s.data ? [s.data as DriftStatus] : [])))
  const syncing = releases.some((r) => ACTIVE.has(r.sync_status))
  const lastSync = releases
    .map((r) => r.last_synced_at)
    .filter((at): at is string => !!at)
    .sort()
    .at(-1)
  const remove = useDeleteProject()
  const client = useQueryClient()
  const [syncError, setSyncError] = useState(false)

  async function syncAll() {
    setSyncError(false)
    try {
      await Promise.all(releases.map((r) => startSync(project.slug, r.name)))
    } catch {
      setSyncError(true)
    }
    await client.invalidateQueries({ queryKey: ['projects'] })
  }

  return (
    <tr className="border-t border-zinc-100 dark:border-zinc-800">
      <td className="px-4 py-3">
        <Link to={`/p/${project.slug}`} className="font-medium hover:underline">
          {project.slug}
        </Link>
        <p className="text-xs text-zinc-500">
          {trackerLabel(project.tracker, project.tracker_key)}
        </p>
      </td>
      <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
        {project.repository ? (
          <span className="flex items-center gap-1.5">
            <GitHubIcon className="size-3.5" />
            {project.repository}
          </span>
        ) : (
          <span className="text-zinc-400">Issues only</span>
        )}
      </td>
      <td className="num px-4 py-3 text-zinc-600 dark:text-zinc-400">
        {count(releases.length, 'release')}
      </td>
      <td className="px-4 py-3">
        {syncing ? (
          <span className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400">
            <RefreshCw className="size-3 animate-spin" aria-hidden />
            Syncing
          </span>
        ) : worst ? (
          <Pill tone={STATUS_STYLES[worst].tone}>{STATUS_STYLES[worst].label}</Pill>
        ) : (
          <span className="text-xs text-zinc-400">–</span>
        )}
      </td>
      <td className="px-4 py-3 text-zinc-500">
        {syncError ? (
          <span className="text-rose-600">Sync failed to start</span>
        ) : (
          relativeTime(lastSync)
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex justify-end gap-1.5">
          <Button
            variant="secondary"
            size="sm"
            disabled={syncing || !releases.length}
            onClick={syncAll}
            title={releases.length ? 'Sync every tracked release' : 'Open a release to sync it'}
          >
            <RefreshCw className="size-3.5" />
            Sync
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Remove ${project.slug}`}
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Remove ${project.slug} and all of its synced data?`)) {
                remove.mutate(project.slug)
              }
            }}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  )
}

function EmptyState() {
  return (
    <Card className="flex flex-col items-center px-6 py-14 text-center">
      <h2 className="text-sm font-semibold">No projects yet</h2>
      <p className="mt-1 max-w-sm text-sm text-zinc-500">
        Connect a Jira project or a GitHub repository&rsquo;s issues and, optionally, the repository
        that implements them. The first sync takes a minute or two.
      </p>
      <Link to="/projects/new" className={buttonClass('primary', 'md', 'mt-5')}>
        <Plus className="size-4" />
        Connect project
      </Link>
    </Card>
  )
}
