import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router'

import type { Project } from '../api/client'
import { useDrift, useNarrative, useProjects, useReleases, type Period } from '../api/hooks'
import { Crumb, PageHeader } from '../components/AppShell'
import { AttentionCard } from '../components/dashboard/AttentionCard'
import { KpiTiles } from '../components/dashboard/KpiTiles'
import { PeriodPicker } from '../components/dashboard/PeriodPicker'
import { SyncControl } from '../components/dashboard/SyncControl'
import { Verdict } from '../components/dashboard/Verdict'
import { NarrativePanel } from '../components/NarrativePanel'
import { Card, ErrorNotice, Spinner } from '../components/ui'
import {
  isoDate,
  PERIOD_PRESETS,
  periodProblem,
  presetRange,
  type PeriodPreset,
} from '../lib/format'
import { defaultRelease, releasePath } from '../lib/routes'
import { useUrlState } from '../lib/useUrlState'

// The chart library is the largest dependency; load it after the first paint.
const BurnupChart = lazy(() =>
  import('../components/dashboard/BurnupChart').then((m) => ({ default: m.BurnupChart })),
)

const HIGHLIGHT_MS = 2500

/** `/p/:slug`: open the project's most relevant release. */
export function ProjectIndex() {
  const { slug = '' } = useParams()
  const projects = useProjects()
  const releases = useReleases(slug)
  const project = projects.data?.find((p) => p.slug === slug)

  if (projects.data && !project) return <NotFound what={`project “${slug}”`} />
  if (releases.error) return <ErrorNotice error={releases.error} />
  if (!project || !releases.data) return <Spinner label="Loading releases…" className="p-6" />

  const tracked = project.tracked_releases.filter((r) => !r.released)
  const name = defaultRelease(tracked.length ? tracked : releases.data)
  if (!name) return <NotFound what={`any release in ${project.tracker_key}`} />
  return <Navigate to={releasePath(slug, name)} replace />
}

/** `/`: the most relevant tracked release, else the projects list. */
export function OverviewRedirect() {
  const projects = useProjects()
  if (projects.error) return <ErrorNotice error={projects.error} />
  if (!projects.data) return <Spinner label="Loading…" className="p-6" />
  const project = projects.data.find((p) => p.tracked_releases.some((r) => !r.released))
  const release = project && defaultRelease(project.tracked_releases.filter((r) => !r.released))
  if (project && release) return <Navigate to={releasePath(project.slug, release)} replace />
  if (projects.data.length) return <Navigate to={`/p/${projects.data[0].slug}`} replace />
  return <Navigate to="/projects" replace />
}

export function DashboardPage() {
  const { slug = '', release = '' } = useParams()
  const projects = useProjects()
  const project = projects.data?.find((p) => p.slug === slug)

  if (projects.error) return <ErrorNotice error={projects.error} />
  if (!projects.data) return <Spinner label="Loading…" className="p-6" />
  if (!project) return <NotFound what={`project “${slug}”`} />
  return <Dashboard key={`${slug}/${release}`} project={project} release={release} />
}

function Dashboard({ project, release }: { project: Project; release: string }) {
  const [today] = useState(() => isoDate(new Date()))
  const defaults = presetRange('8w', today)
  const [state, setState] = useUrlState({ period: '8w', from: defaults.from, to: defaults.to })
  const preset: PeriodPreset =
    state.period in PERIOD_PRESETS || state.period === 'custom'
      ? (state.period as PeriodPreset)
      : '8w'
  const { from, to } =
    preset === 'custom' ? { from: state.from, to: state.to } : presetRange(preset, today)
  const period: Period = useMemo(() => ({ from, to }), [from, to])
  const problem = periodProblem(period.from, period.to)

  const location = useLocation()
  const initialJobId = (location.state as { jobId?: number } | null)?.jobId
  const releases = useReleases(project.slug)
  const drift = useDrift(project.slug, release, period, problem === null)
  const [explain, setExplain] = useState(false)
  const narrative = useNarrative(project.slug, release, period, problem === null && explain)
  const [highlighted, setHighlighted] = useState<string | null>(null)
  const tracked = project.tracked_releases.find((r) => r.name === release)
  const stored = releases.data?.find((r) => r.name === release)

  useEffect(() => {
    if (!highlighted) return
    const timer = window.setTimeout(() => setHighlighted(null), HIGHLIGHT_MS)
    return () => window.clearTimeout(timer)
  }, [highlighted])

  function highlight(section: string) {
    setHighlighted(section)
    document
      .querySelector(`[data-sections~="${section}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  function requestExplanation() {
    setExplain(true)
    document.getElementById('narrative')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <PageHeader
        crumbs={
          <>
            <Crumb to="/projects">{project.slug}</Crumb>
            <ReleaseSwitcher
              project={project}
              release={release}
              names={releases.data?.map((r) => r.name)}
            />
          </>
        }
        actions={
          <>
            <PeriodPicker
              preset={preset}
              from={period.from}
              to={period.to}
              today={today}
              onChange={(patch) =>
                setState({
                  ...patch,
                  ...(patch.period && patch.period !== 'custom' ? { from: '', to: '' } : {}),
                })
              }
            />
            <SyncControl
              slug={project.slug}
              release={release}
              tracked={tracked}
              initialJobId={initialJobId}
            />
          </>
        }
      />
      <main className="flex-1 p-6">
        <div className="mx-auto max-w-6xl space-y-6">
          {problem && (
            <p role="alert" className="text-sm text-amber-700 dark:text-amber-400">
              {problem}
            </p>
          )}
          {drift.error && <ErrorNotice error={drift.error} />}
          {drift.isLoading && <Spinner label="Computing drift…" />}
          {drift.data && (
            <>
              {!drift.data.coverage.complete && (
                <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                  {drift.data.coverage.notes.join(' ')} Use <strong>Sync</strong> to fetch the
                  latest data.
                </div>
              )}
              <Verdict
                report={drift.data}
                slug={project.slug}
                storedTarget={stored?.target_date}
                tracker={project.tracker}
                highlighted={highlighted === 'forecast'}
                onExplain={requestExplanation}
              />
              <KpiTiles
                report={drift.data}
                searchTemplate={project.search_url_template}
                tracker={project.tracker}
                highlighted={highlighted}
              />
              <section className="grid gap-4 xl:grid-cols-5">
                <Suspense
                  fallback={
                    <Card className="p-5 xl:col-span-3">
                      <Spinner label="Loading chart…" />
                    </Card>
                  }
                >
                  <BurnupChart
                    report={drift.data}
                    trackerKey={project.tracker_key}
                    tracker={project.tracker}
                    highlighted={highlighted === 'throughput'}
                  />
                </Suspense>
                <AttentionCard
                  report={drift.data}
                  itemTemplate={project.item_url_template}
                  searchTemplate={project.search_url_template}
                  tracker={project.tracker}
                  highlighted={highlighted === 'code'}
                />
              </section>
              <NarrativePanel
                narrative={narrative.data}
                loading={narrative.isFetching}
                error={narrative.error}
                requested={explain}
                onExplain={requestExplanation}
                onEvidence={highlight}
                itemUrlTemplate={project.item_url_template}
                searchUrlTemplate={project.search_url_template}
                tracker={project.tracker}
              />
            </>
          )}
        </div>
      </main>
    </>
  )
}

function ReleaseSwitcher({
  project,
  release,
  names,
}: {
  project: Project
  release: string
  names: string[] | undefined
}) {
  const navigate = useNavigate()
  const options = names?.includes(release) ? names : [release, ...(names ?? [])]
  return (
    <select
      aria-label="Release"
      value={release}
      onChange={(e) =>
        navigate(`${releasePath(project.slug, e.target.value)}${window.location.search}`)
      }
      className="-ml-1 rounded-md border-0 bg-transparent py-0.5 pr-7 pl-1 text-sm font-medium hover:bg-zinc-100 focus:ring-2 focus:ring-blue-600/20 focus:outline-none dark:hover:bg-zinc-800"
    >
      {options.map((name) => (
        <option key={name} value={name}>
          {name}
        </option>
      ))}
    </select>
  )
}

function NotFound({ what }: { what: string }) {
  return (
    <main className="p-6">
      <p className="text-sm text-zinc-500">
        Could not find {what}.{' '}
        <Link to="/projects" className="font-medium text-blue-600 hover:underline">
          Back to projects
        </Link>
      </p>
    </main>
  )
}
