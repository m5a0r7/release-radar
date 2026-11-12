import { ChevronsUpDown, Folder, LayoutGrid, Settings } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation, useParams } from 'react-router'

import type { DriftStatus, Project } from '../api/client'
import { useMe, useProjects, useReleaseStatuses } from '../api/hooks'
import { cn } from '../lib/cn'
import { STATUS_STYLES } from '../lib/format'
import { releasePath } from '../lib/routes'
import { Avatar, ErrorNotice, Logo, Spinner } from './ui'

/** Signed-in layout: sends signed-out visitors to the login page and back afterwards. */
export function AppShell() {
  const me = useMe()
  const location = useLocation()

  if (me.isPending) return <Spinner label="Loading…" className="p-6" />
  if (me.error) return <ErrorNotice error={me.error} />
  if (me.data === null) {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }

  const { user, workspace } = me.data
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50 px-3 py-4 dark:border-zinc-800 dark:bg-zinc-950">
        <Link to="/" className="px-2">
          <Logo />
        </Link>
        <div
          className="mt-5 flex items-center justify-between rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900"
          title="Workspaces you belong to"
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="grid size-5 shrink-0 place-items-center rounded bg-zinc-900 text-[10px] font-semibold text-white dark:bg-zinc-100 dark:text-zinc-900">
              {workspace.name[0]?.toUpperCase()}
            </span>
            <span className="truncate">{workspace.name}</span>
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-zinc-400" aria-hidden />
        </div>
        <nav className="mt-5 space-y-0.5">
          <NavItem to="/" icon={<LayoutGrid className="size-4" />} end>
            Overview
          </NavItem>
          <NavItem to="/projects" icon={<Folder className="size-4" />}>
            Projects
          </NavItem>
          <NavItem to="/settings" icon={<Settings className="size-4" />}>
            Settings
          </NavItem>
        </nav>
        <TrackedReleases />
        <div className="mt-auto flex items-center gap-2 border-t border-zinc-200 px-2 pt-3 dark:border-zinc-800">
          <Avatar name={user.name} url={user.avatar_url} />
          <div className="min-w-0 text-xs">
            <p className="truncate font-medium">{user.name}</p>
            <p className="text-zinc-500">
              {user.provider === 'github' ? 'Signed in with GitHub' : 'Demo account'}
            </p>
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  )
}

function NavItem({
  to,
  icon,
  end,
  children,
}: {
  to: string
  icon: ReactNode
  end?: boolean
  children: ReactNode
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
          isActive
            ? 'bg-zinc-200/60 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
            : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900',
        )
      }
    >
      {icon}
      {children}
    </NavLink>
  )
}

function TrackedReleases() {
  const projects = useProjects()
  if (!projects.data?.length) return null
  return (
    <div className="mt-6 min-h-0 flex-1 space-y-4 overflow-y-auto">
      {projects.data.map((project) => (
        <ProjectReleases key={project.slug} project={project} />
      ))}
    </div>
  )
}

function ProjectReleases({ project }: { project: Project }) {
  const params = useParams()
  const releases = project.tracked_releases
  const statuses = useReleaseStatuses(
    releases.map((r) => ({ slug: project.slug, release: r.name })),
  )
  return (
    <div>
      <Link
        to={`/p/${project.slug}`}
        className="block px-2 text-[11px] font-medium tracking-wider text-zinc-400 uppercase hover:text-zinc-600"
      >
        {project.slug}
      </Link>
      <div className="mt-1 space-y-0.5">
        {releases.map((release, index) => {
          const active = params.slug === project.slug && params.release === release.name
          const status = statuses[index]?.data as DriftStatus | undefined
          return (
            <Link
              key={release.name}
              to={releasePath(project.slug, release.name)}
              className={cn(
                'flex items-center justify-between rounded-md px-2 py-1 text-[13px]',
                active
                  ? 'bg-zinc-200/60 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
                  : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900',
              )}
            >
              <span className="truncate">{release.name}</span>
              <span
                className={cn(
                  'size-1.5 shrink-0 rounded-full',
                  status ? STATUS_STYLES[status].dot : 'bg-zinc-300 dark:bg-zinc-700',
                )}
                title={status ? STATUS_STYLES[status].label : undefined}
              />
            </Link>
          )
        })}
        {!releases.length && <p className="px-2 py-1 text-xs text-zinc-400">No release synced</p>}
      </div>
    </div>
  )
}

/** The bar at the top of every signed-in page. */
export function PageHeader({ crumbs, actions }: { crumbs: ReactNode; actions?: ReactNode }) {
  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-zinc-200 bg-white px-6 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex min-w-0 items-center gap-2 text-sm">{crumbs}</div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  )
}

export function Crumb({ to, children }: { to?: string; children: ReactNode }) {
  return to ? (
    <>
      <Link to={to} className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        {children}
      </Link>
      <span className="text-zinc-300 dark:text-zinc-700">/</span>
    </>
  ) : (
    <span className="font-medium">{children}</span>
  )
}
