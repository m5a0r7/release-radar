import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { ApiError } from '../api/client'
import { useAuthConfig, useDemoSignIn, useMe } from '../api/hooks'
import { buttonClass } from '../components/styles'
import { Button, ErrorNotice, GitHubIcon, Logo, Pill, Spinner } from '../components/ui'

/** Only same-app paths, mirroring the API's open-redirect guard. */
function safeNext(value: string | null): string {
  return value && /^\/(?!\/)/.test(value) ? value : '/'
}

export function LoginPage() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const me = useMe()
  const config = useAuthConfig()
  const demo = useDemoSignIn()
  const navigate = useNavigate()
  const signInError = params.get('error')

  if (me.data) return <Navigate to={next} replace />

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col justify-between bg-white p-10 dark:bg-zinc-900">
        <Logo />
        <div className="mx-auto w-full max-w-sm py-12">
          <h1 className="text-2xl font-semibold tracking-tight">Sign in to Release Radar</h1>
          <p className="mt-2 text-sm text-zinc-500">
            Know if your release will ship on time, and why. New here? Signing in creates your
            account.
          </p>

          <div className="mt-8 space-y-3">
            {config.isPending && <Spinner label="Loading sign-in options…" />}
            {config.error && <ErrorNotice error={config.error} />}
            {config.data?.github && (
              <a
                href={`/v1/auth/github/login?next=${encodeURIComponent(next)}`}
                className={buttonClass('primary', 'lg', 'w-full')}
              >
                <GitHubIcon className="size-4" />
                Continue with GitHub
              </a>
            )}
            {config.data?.demo && (
              <Button
                variant={config.data.github ? 'secondary' : 'primary'}
                size="lg"
                className="w-full"
                disabled={demo.isPending}
                onClick={() =>
                  demo.mutate(undefined, { onSuccess: () => navigate(next, { replace: true }) })
                }
              >
                {demo.isPending ? 'Signing in…' : 'Try the demo account'}
              </Button>
            )}
            {config.data?.demo_until && (
              <p className="text-center text-xs text-zinc-500">
                The shared demo account is open until{' '}
                {new Date(`${config.data.demo_until}T00:00:00Z`).toLocaleDateString(undefined, {
                  dateStyle: 'long',
                  timeZone: 'UTC',
                })}
                .
              </p>
            )}
            {config.data && !config.data.github && !config.data.demo && (
              <p className="text-sm text-zinc-500">
                No sign-in method is configured. Set GITHUB_OAUTH_CLIENT_ID and
                GITHUB_OAUTH_CLIENT_SECRET on the server.
              </p>
            )}
            {demo.error && <ErrorNotice error={demo.error} />}
            {signInError && <ErrorNotice error={new ApiError(400, { title: signInError })} />}
          </div>

          <p className="mt-8 text-xs text-zinc-400">
            Release Radar only reads issues and pull requests. GitHub sign-in asks for no
            permissions, and nothing is written back to Jira or GitHub.
          </p>
        </div>
        <p className="text-xs text-zinc-400">Release Radar</p>
      </div>

      <div className="hidden items-center justify-center border-l border-zinc-200 bg-zinc-50 p-12 lg:flex dark:border-zinc-800 dark:bg-zinc-950">
        <div className="w-full max-w-md" aria-hidden>
          <div className="rounded-lg border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-zinc-500">kafka · 4.5.0</p>
              <Pill tone="amber">At risk</Pill>
            </div>
            <p className="num mt-3 text-3xl font-semibold tracking-tight">37%</p>
            <p className="text-sm text-zinc-500">chance of shipping by the target date</p>
            <div className="mt-4 rounded-md bg-zinc-50 p-3 text-sm text-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-300">
              86% of the work completed this period was never in the plan: tickets join the release
              when they are resolved.
              <div className="mt-2 flex gap-1.5">
                <EvidenceTag>E11 unplanned 86%</EvidenceTag>
                <EvidenceTag>E6 resolved 121</EvidenceTag>
              </div>
            </div>
          </div>
          <p className="mt-6 text-center text-sm text-zinc-500">
            Plan vs. reality from Jira and GitHub, explained with evidence.
          </p>
        </div>
      </div>
    </div>
  )
}

function EvidenceTag({ children }: { children: string }) {
  return (
    <span className="rounded border border-zinc-200 bg-white px-1.5 text-[11px] text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400">
      {children}
    </span>
  )
}
