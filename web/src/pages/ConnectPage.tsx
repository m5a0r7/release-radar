import { AlertTriangle, Check, Search } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'

import type { CodeCheck, TrackerCheck as TrackerCheckOut } from '../api/client'
import {
  startSync,
  useCodeCheck,
  useCreateProject,
  useRepositorySearch,
  useSetTargetDate,
  useTrackerCheck,
} from '../api/hooks'
import { Crumb, PageHeader } from '../components/AppShell'
import { inputClass } from '../components/styles'
import { Button, Card, ErrorNotice, Field, Input, Spinner } from '../components/ui'
import { cn } from '../lib/cn'
import { percent } from '../lib/format'
import { defaultRelease, releasePath } from '../lib/routes'
import { trackerName, type TrackerKind } from '../lib/tracker'

const REPOSITORY = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/
/** Below this share of PRs mentioning a ticket, code metrics say little. */
const WEAK_LINKING = 0.2

type TrackerCheck = TrackerCheckOut & { tracker: TrackerKind }

const TRACKER_OPTIONS: { value: TrackerKind; label: string }[] = [
  { value: 'jira', label: 'Jira' },
  { value: 'github', label: 'GitHub Issues' },
]

type Step = 1 | 2 | 3

export function ConnectPage() {
  const [step, setStep] = useState<Step>(1)
  const [tracker, setTracker] = useState<TrackerCheck>()
  const [code, setCode] = useState<CodeCheck | null>()

  return (
    <>
      <PageHeader
        crumbs={
          <>
            <Crumb to="/projects">Projects</Crumb>
            <Crumb>Connect</Crumb>
          </>
        }
      />
      <main className="flex-1 p-6">
        <div className="mx-auto max-w-2xl">
          <h1 className="text-xl font-semibold tracking-tight">Connect a project</h1>
          <ol className="mt-5 flex items-center gap-3">
            <StepLabel n={1} current={step}>
              Plan
            </StepLabel>
            <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
            <StepLabel n={2} current={step}>
              Code repository
            </StepLabel>
            <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
            <StepLabel n={3} current={step}>
              Release &amp; target
            </StepLabel>
          </ol>
          <Card className="mt-6 p-6">
            {step === 1 && (
              <TrackerStep
                initial={tracker}
                onDone={(checked) => {
                  if (checked.key !== tracker?.key || checked.tracker !== tracker?.tracker)
                    setCode(undefined)
                  setTracker(checked)
                  setStep(2)
                }}
              />
            )}
            {step === 2 && tracker && (
              <CodeStep
                tracker={tracker}
                initial={code}
                onBack={() => setStep(1)}
                onDone={(checked) => {
                  setCode(checked)
                  setStep(3)
                }}
              />
            )}
            {step === 3 && tracker && code !== undefined && (
              <ReleaseStep tracker={tracker} code={code} onBack={() => setStep(2)} />
            )}
          </Card>
        </div>
      </main>
    </>
  )
}

function StepLabel({ n, current, children }: { n: Step; current: Step; children: ReactNode }) {
  const state = n < current ? 'done' : n === current ? 'now' : 'next'
  return (
    <li
      className={cn(
        'flex items-center gap-2 text-sm',
        state === 'next' ? 'text-zinc-400' : 'text-zinc-900 dark:text-zinc-100',
        state === 'now' && 'font-medium',
      )}
      aria-current={state === 'now' ? 'step' : undefined}
    >
      <span
        className={cn(
          'grid size-6 place-items-center rounded-full text-xs',
          state === 'done' && 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900',
          state === 'now' && 'border-2 border-zinc-900 font-semibold dark:border-zinc-100',
          state === 'next' && 'border border-zinc-300 dark:border-zinc-700',
        )}
      >
        {state === 'done' ? <Check className="size-3.5" /> : n}
      </span>
      {children}
    </li>
  )
}

function Summary({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md bg-zinc-50 px-3 py-2 text-sm dark:bg-zinc-800/50">
      <span className="text-zinc-500">{label}</span>
      <span className="truncate font-medium">{children}</span>
    </div>
  )
}

function TrackerStep({
  initial,
  onDone,
}: {
  initial?: TrackerCheck
  onDone: (checked: TrackerCheck) => void
}) {
  const [kind, setKind] = useState<TrackerKind>(initial?.tracker ?? 'jira')
  const [key, setKey] = useState(initial?.key ?? '')
  const check = useTrackerCheck()
  const checked = check.data && check.variables?.tracker === kind ? check.data : undefined
  const result: TrackerCheck | undefined =
    checked?.key.toLowerCase() === key.toLowerCase()
      ? { ...checked, tracker: kind }
      : initial?.tracker === kind && initial.key === key
        ? initial
        : undefined
  const github = kind === 'github'
  const valid = github ? REPOSITORY.test(key) : key.length >= 2

  function submit(event: FormEvent) {
    event.preventDefault()
    if (result && !result.already_connected_as) onDone(result)
    else check.mutate({ tracker: kind, tracker_key: key })
  }

  function choose(next: TrackerKind) {
    setKind(next)
    setKey('')
    check.reset()
  }

  return (
    <form onSubmit={submit}>
      <h2 className="text-sm font-semibold">Where is the release planned?</h2>
      <div
        role="radiogroup"
        aria-label="Tracker"
        className="mt-3 inline-flex rounded-md border border-zinc-200 p-0.5 dark:border-zinc-800"
      >
        {TRACKER_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={kind === option.value}
            onClick={() => choose(option.value)}
            className={cn(
              'rounded px-3 py-1 text-sm',
              kind === option.value
                ? 'bg-zinc-900 font-medium text-white dark:bg-zinc-100 dark:text-zinc-900'
                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100',
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
      <p className="mt-3 text-sm text-zinc-500">
        {github ? (
          <>
            Milestones are releases and the issues in a milestone are its scope. Use the
            repository&rsquo;s <span className="font-mono text-xs">owner/name</span>.
          </>
        ) : (
          <>
            The project key is the prefix of its ticket numbers, like <code>KAFKA</code> in
            KAFKA-1234.
          </>
        )}
      </p>
      <div className="mt-4">
        <Field label={github ? 'Repository' : 'Project key'}>
          <Input
            value={key}
            onChange={(e) =>
              setKey(
                github
                  ? e.target.value.trim()
                  : e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''),
              )
            }
            placeholder={github ? 'apache/arrow' : 'KAFKA'}
            autoFocus
            maxLength={github ? 140 : 20}
          />
        </Field>
      </div>
      {check.isPending && (
        <Spinner label={`Looking up the project in ${trackerName(kind)}…`} className="mt-4" />
      )}
      {check.error && (
        <div className="mt-4">
          <ErrorNotice error={check.error} />
        </div>
      )}
      {result && (
        <div className="mt-4 space-y-3">
          <Summary label={trackerName(kind)}>
            {github ? result.key : `${result.name} · ${result.key}`} ·{' '}
            {result.upcoming_releases.length} upcoming {github ? 'milestones' : 'releases'}
          </Summary>
          {result.already_connected_as && (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              This workspace already tracks {result.key} as{' '}
              <Link className="font-medium underline" to={`/p/${result.already_connected_as}`}>
                {result.already_connected_as}
              </Link>
              .
            </p>
          )}
        </div>
      )}
      <div className="mt-6 flex justify-between">
        <Link to="/projects" className="text-sm text-zinc-500 hover:text-zinc-900">
          Cancel
        </Link>
        <Button
          type="submit"
          disabled={!valid || check.isPending || !!result?.already_connected_as}
        >
          {result ? 'Continue' : 'Check project'}
        </Button>
      </div>
    </form>
  )
}

function TrackerSummary({ tracker }: { tracker: TrackerCheck }) {
  return (
    <Summary label={trackerName(tracker.tracker)}>
      {tracker.tracker === 'github' ? tracker.key : `${tracker.name} · ${tracker.key}`}
    </Summary>
  )
}

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms)
    return () => window.clearTimeout(timer)
  }, [value, ms])
  return debounced
}

function CodeStep({
  tracker,
  initial,
  onBack,
  onDone,
}: {
  tracker: TrackerCheck
  initial?: CodeCheck | null
  onBack: () => void
  onDone: (checked: CodeCheck | null) => void
}) {
  const github = tracker.tracker === 'github'
  const [query, setQuery] = useState(initial?.repository ?? (github ? tracker.key : ''))
  const search = useRepositorySearch(useDebounced(query.trim(), 300))
  const check = useCodeCheck()
  const result = check.data ?? initial ?? undefined
  const typed = query.trim()
  const { mutate } = check

  function choose(repository: string) {
    setQuery(repository)
    mutate({ repository, tracker: tracker.tracker, tracker_key: tracker.key })
  }

  // Issues and pull requests usually live in the same repository; check it straight away.
  useEffect(() => {
    if (github && initial === undefined)
      mutate({ repository: tracker.key, tracker: 'github', tracker_key: tracker.key })
  }, [github, initial, mutate, tracker.key])

  const options = search.data ?? []
  const offerTyped =
    REPOSITORY.test(typed) &&
    !options.some((o) => o.full_name.toLowerCase() === typed.toLowerCase())

  return (
    <div>
      <TrackerSummary tracker={tracker} />
      <h2 className="mt-6 text-sm font-semibold">
        Which repository implements these {github ? 'issues' : 'tickets'}?
      </h2>
      <p className="mt-1 text-sm text-zinc-500">
        Search public GitHub repositories or paste{' '}
        <span className="font-mono text-xs">owner/name</span>.{' '}
        {github ? (
          <>
            Its pull requests should reference issues, like <code>Fixes #123</code>.
          </>
        ) : (
          <>Its pull requests should mention {tracker.key} tickets.</>
        )}
      </p>
      <div className="relative mt-3">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-zinc-400"
          aria-hidden
        />
        <input
          className={cn(inputClass, 'pl-9')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="apache/kafka"
          aria-label="Repository"
          autoFocus
        />
      </div>
      {search.error && (
        <div className="mt-2">
          <ErrorNotice error={search.error} />
        </div>
      )}
      {typed.length >= 2 && (offerTyped || options.length > 0) && (
        <ul className="mt-2 space-y-0.5" aria-label="Repositories">
          {offerTyped && (
            <RepoOption
              name={typed}
              detail="Use this repository"
              selected={result?.repository.toLowerCase() === typed.toLowerCase()}
              onSelect={() => choose(typed)}
            />
          )}
          {options.slice(0, 6).map((repo) => (
            <RepoOption
              key={repo.full_name}
              name={repo.full_name}
              detail={[repo.language, `★ ${repo.stars.toLocaleString()}`]
                .filter(Boolean)
                .join(' · ')}
              selected={result?.repository === repo.full_name}
              onSelect={() => choose(repo.full_name)}
            />
          ))}
        </ul>
      )}

      {check.isPending && (
        <Spinner label="Checking recent pull requests for ticket references…" className="mt-5" />
      )}
      {check.error && (
        <div className="mt-5">
          <ErrorNotice error={check.error} />
        </div>
      )}
      {result && !check.isPending && <LinkingResult result={result} tracker={tracker} />}

      <div className="mt-6 flex items-center justify-between">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => onDone(null)}>
            Skip, {github ? 'issues' : 'Jira'} only
          </Button>
          <Button disabled={!result || check.isPending} onClick={() => result && onDone(result)}>
            Continue
          </Button>
        </div>
      </div>
    </div>
  )
}

function RepoOption({
  name,
  detail,
  selected,
  onSelect,
}: {
  name: string
  detail: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          'flex w-full items-center justify-between rounded-md px-3 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800',
          selected && 'bg-zinc-100 dark:bg-zinc-800',
        )}
      >
        <span>
          <span className="text-sm font-medium">{name}</span>
          <span className="ml-2 text-xs text-zinc-500">{detail}</span>
        </span>
        {selected && <Check className="size-4" aria-label="Selected" />}
      </button>
    </li>
  )
}

function LinkingResult({ result, tracker }: { result: CodeCheck; tracker: TrackerCheck }) {
  const share = result.linked_share ?? 0
  const ticket = tracker.tracker === 'github' ? 'an issue' : `a ${tracker.key} ticket`
  const name = trackerName(tracker.tracker)
  const good = result.sampled > 0 && share >= WEAK_LINKING
  return (
    <div
      className={cn(
        'mt-5 rounded-md border p-4',
        good
          ? 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-500/30 dark:bg-emerald-500/10'
          : 'border-amber-200 bg-amber-50/60 dark:border-amber-500/30 dark:bg-amber-500/10',
      )}
      role="status"
    >
      <p
        className={cn(
          'flex items-center gap-2 text-sm font-medium',
          good ? 'text-emerald-800 dark:text-emerald-300' : 'text-amber-800 dark:text-amber-300',
        )}
      >
        {good ? <Check className="size-4" /> : <AlertTriangle className="size-4" />}
        {result.sampled === 0
          ? `${result.repository} has no pull requests yet`
          : good
            ? `Linking works: ${result.linked} of the last ${result.sampled} pull requests reference ${ticket}`
            : `Only ${result.linked} of the last ${result.sampled} pull requests (${percent(share)}) reference ${ticket}`}
      </p>
      <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
        {good
          ? `Code metrics (done in code but open in ${name}, PRs without a ticket) will be available.`
          : `Code metrics will be sparse. Check the repository, or continue with ${name} only.`}
      </p>
      {result.samples.length > 0 && (
        <ul className="mt-3 space-y-1">
          {result.samples.map((sample) => (
            <li
              key={sample.number}
              className={cn(
                'flex items-center gap-2 text-xs',
                sample.linked ? 'text-zinc-700 dark:text-zinc-300' : 'text-zinc-400',
              )}
            >
              <span
                className={cn(
                  'size-1.5 shrink-0 rounded-full',
                  sample.linked ? 'bg-emerald-500' : 'bg-zinc-300 dark:bg-zinc-600',
                )}
              />
              <span className="truncate">
                #{sample.number} {sample.title}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function slugFor(key: string): string {
  return (
    (key.split('/').pop() ?? key)
      .toLowerCase()
      .replace(/[^a-z0-9-]/g, '-')
      .replace(/^-+/, '')
      .slice(0, 64) || 'project'
  )
}

function ReleaseStep({
  tracker,
  code,
  onBack,
}: {
  tracker: TrackerCheck
  code: CodeCheck | null
  onBack: () => void
}) {
  const releases = tracker.upcoming_releases
  const [slug, setSlug] = useState(() => slugFor(tracker.key))
  const [release, setRelease] = useState(
    () => defaultRelease(releases.map((name) => ({ name, released: false }))) ?? '',
  )
  const [target, setTarget] = useState('')
  const [error, setError] = useState<unknown>()
  const [busy, setBusy] = useState(false)
  // Retrying after a failed sync start must not try to create the project twice.
  const [created, setCreated] = useState<string>()
  const create = useCreateProject()
  const setTargetDate = useSetTargetDate(slug)
  const navigate = useNavigate()

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(undefined)
    try {
      if (created !== slug) {
        await create.mutateAsync({
          slug,
          tracker: tracker.tracker,
          tracker_key: tracker.key,
          ...(code ? { repository: code.repository } : {}),
        })
        setCreated(slug)
      }
      if (release) {
        if (target) await setTargetDate.mutateAsync({ release, targetDate: target })
        const jobId = await startSync(slug, release)
        navigate(releasePath(slug, release), { state: { jobId } })
      } else {
        navigate(`/p/${slug}`)
      }
    } catch (failure) {
      setError(failure)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="space-y-2">
        <TrackerSummary tracker={tracker} />
        <Summary label="Code">{code ? code.repository : 'Not connected'}</Summary>
      </div>
      <Field
        label="Release to track"
        hint="You can open any other release from the dashboard later."
      >
        {releases.length ? (
          <select
            className={inputClass}
            value={release}
            onChange={(e) => setRelease(e.target.value)}
          >
            {releases.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-sm text-zinc-500">
            {tracker.key} has no upcoming{' '}
            {tracker.tracker === 'github' ? 'milestones' : 'releases in Jira'}, so there is nothing
            to forecast yet.
          </p>
        )}
      </Field>
      {releases.length > 0 && (
        <Field
          label="Target date (optional)"
          hint={`When you need it to ship. Leave empty to use the ${tracker.tracker === 'github' ? 'milestone due date' : 'release date set in Jira'}.`}
        >
          <Input type="date" value={target} onChange={(e) => setTarget(e.target.value)} />
        </Field>
      )}
      <Field label="Name" hint="Lowercase letters, numbers and dashes; used in links.">
        <Input
          value={slug}
          onChange={(e) => setSlug(e.target.value.toLowerCase())}
          disabled={created !== undefined}
          pattern="[a-z0-9][a-z0-9\-]{0,63}"
          required
        />
      </Field>
      {error !== undefined && <ErrorNotice error={error} />}
      <div className="flex justify-between">
        <Button variant="secondary" onClick={onBack} disabled={busy}>
          Back
        </Button>
        <Button type="submit" disabled={busy}>
          {busy ? 'Connecting…' : release ? 'Connect and sync' : 'Connect'}
        </Button>
      </div>
    </form>
  )
}
