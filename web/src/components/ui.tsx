import type { ReactNode } from 'react'

import { ApiError } from '../api/client'

export function Card({
  title,
  action,
  highlighted = false,
  id,
  children,
  className = '',
}: {
  title?: string
  action?: ReactNode
  highlighted?: boolean
  id?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section
      id={id}
      className={`rounded-xl bg-white p-5 shadow-sm ring-1 transition-shadow ${
        highlighted ? 'ring-2 ring-indigo-400 shadow-md' : 'ring-slate-200'
      } ${className}`}
    >
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-slate-900">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

export function Button({
  children,
  variant = 'primary',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' }) {
  const styles =
    variant === 'primary'
      ? 'bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-indigo-300'
      : 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:text-slate-400'
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function ErrorNotice({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError
      ? `${error.message}${error.detail ? ` — ${error.detail}` : ''}`
      : 'Something went wrong. Is the API running?'
  return (
    <div
      role="alert"
      className="rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-800 ring-1 ring-rose-200"
    >
      {message}
    </div>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500" role="status">
      <span className="size-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
      {label}
    </div>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
      {label}
      {children}
    </label>
  )
}

export const inputClass =
  'rounded-lg border-0 bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-slate-300 focus:ring-2 focus:ring-indigo-500 focus:outline-none'
