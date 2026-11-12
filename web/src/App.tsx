import { lazy, Suspense, useEffect, useMemo, useState } from 'react'

import type { Release } from './api/client'
import { useDrift, useNarrative, useProjects, useReleases, type Period } from './api/hooks'
import { AddProjectForm } from './components/AddProjectForm'
import { HealthCard } from './components/HealthCard'
import { MetricsGrid } from './components/MetricsGrid'
import { NarrativePanel } from './components/NarrativePanel'
import { SyncButton } from './components/SyncButton'
import { ErrorNotice, Field, inputClass, Spinner } from './components/ui'
import { daysBefore, isoDate, periodProblem } from './lib/format'
import { useUrlState } from './lib/useUrlState'

// The chart library is the largest dependency; load it after the first paint.
const ThroughputChart = lazy(() =>
  import('./components/ThroughputChart').then((m) => ({ default: m.ThroughputChart })),
)

const DEFAULT_PERIOD_DAYS = 56
const HIGHLIGHT_MS = 2500

export default function App() {
  const [today] = useState(() => isoDate(new Date()))
  const [state, setState] = useUrlState({
    project: '',
    release: '',
    from: daysBefore(today, DEFAULT_PERIOD_DAYS - 1),
    to: today,
    target: '',
  })
  const projects = useProjects()
  const releases = useReleases(state.project || undefined)
  const [explainFor, setExplainFor] = useState<string>()
  const [highlighted, setHighlighted] = useState<string | null>(null)

  const project = projects.data?.find((p) => p.slug === state.project)
  const period: Period = useMemo(
    () => ({ from: state.from, to: state.to, targetDate: state.target || undefined }),
    [state.from, state.to, state.target],
  )
  const release = state.release || undefined
  const problem = periodProblem(state.from, state.to)
  const drift = useDrift(project?.slug, release, period, problem === null)
  const narrativeKey = `${state.project}/${state.release}`
  const narrative = useNarrative(
    project?.slug,
    release,
    period,
    problem === null && explainFor === narrativeKey,
  )

  useEffect(() => {
    if (projects.data?.length && !projects.data.some((p) => p.slug === state.project)) {
      setState({ project: projects.data[0].slug, release: '' })
    }
  }, [projects.data, state.project, setState])

  useEffect(() => {
    if (!state.release && releases.data?.length)
      setState({ release: defaultRelease(releases.data) })
  }, [releases.data, state.release, setState])

  function highlight(section: string) {
    setHighlighted(section)
    document
      .querySelector(`[data-section="${section}"], #section-${section}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    window.setTimeout(() => setHighlighted(null), HIGHLIGHT_MS)
  }

  if (projects.isPending)
    return (
      <Shell>
        <Spinner label="Loading projects…" />
      </Shell>
    )
  if (projects.error)
    return (
      <Shell>
        <ErrorNotice error={projects.error} />
      </Shell>
    )
  if (!projects.data.length) {
    return (
      <Shell>
        <AddProjectForm onCreated={(slug) => setState({ project: slug, release: '' })} />
      </Shell>
    )
  }
  if (!project)
    return (
      <Shell>
        <Spinner label="Loading project…" />
      </Shell>
    )

  return (
    <Shell>
      <div className="flex flex-wrap items-end gap-3 rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <Field label="Project">
          <select
            className={inputClass}
            value={state.project}
            onChange={(e) => setState({ project: e.target.value, release: '' })}
          >
            {projects.data.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.slug} ({p.tracker_key})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Release">
          <select
            className={inputClass}
            value={state.release}
            onChange={(e) => setState({ release: e.target.value })}
          >
            {releases.data?.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name} {r.released ? '(released)' : ''}
              </option>
            ))}
          </select>
        </Field>
        <Field label="From">
          <input
            type="date"
            className={inputClass}
            value={state.from}
            max={state.to}
            onChange={(e) => setState({ from: e.target.value })}
          />
        </Field>
        <Field label="To">
          <input
            type="date"
            className={inputClass}
            value={state.to}
            min={state.from}
            max={today}
            onChange={(e) => setState({ to: e.target.value })}
          />
        </Field>
        <Field label="Target date">
          <input
            type="date"
            className={inputClass}
            value={state.target}
            onChange={(e) => setState({ target: e.target.value })}
          />
        </Field>
        {problem && (
          <p role="alert" className="self-center text-xs text-amber-700">
            {problem}
          </p>
        )}
        <div className="ml-auto">
          {release && <SyncButton slug={project.slug} release={release} />}
        </div>
      </div>

      {drift.error && <ErrorNotice error={drift.error} />}
      {drift.isLoading && <Spinner label="Computing drift…" />}

      {drift.data && (
        <>
          {!drift.data.coverage.complete && (
            <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200">
              {drift.data.coverage.notes.join(' ')} Use <strong>Sync now</strong> to fetch the
              latest data.
            </div>
          )}
          <HealthCard report={drift.data} highlighted={highlighted === 'forecast'} />
          <MetricsGrid
            report={drift.data}
            itemUrlTemplate={project.item_url_template}
            highlighted={highlighted}
          />
          <Suspense fallback={<Spinner label="Loading chart…" />}>
            <ThroughputChart report={drift.data} highlighted={highlighted === 'throughput'} />
          </Suspense>
          <NarrativePanel
            narrative={narrative.data}
            loading={narrative.isFetching}
            error={narrative.error}
            requested={explainFor === narrativeKey}
            onExplain={() => setExplainFor(narrativeKey)}
            onEvidence={highlight}
            itemUrlTemplate={project.item_url_template}
          />
        </>
      )}
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-4">
          <span className="grid size-8 place-items-center rounded-lg bg-indigo-600 font-bold text-white">
            R
          </span>
          <div>
            <h1 className="text-base font-semibold text-slate-900">Release Radar</h1>
            <p className="text-xs text-slate-500">
              Is the release drifting from its plan, and why?
            </p>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">{children}</main>
    </div>
  )
}

/** The upcoming release with the highest version, else the newest one. */
function defaultRelease(releases: Release[]): string {
  const upcoming = releases.filter((r) => !r.released)
  const pool = upcoming.length ? upcoming : releases
  return [...pool].sort((a, b) => b.name.localeCompare(a.name, undefined, { numeric: true }))[0]
    .name
}
