import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SVGProps } from 'react'

import { ApiError } from '../api/client'
import { cn } from '../lib/cn'
import { buttonClass, inputClass, type ButtonSize, type ButtonVariant } from './styles'

export function Button({
  variant,
  size,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
}) {
  return <button type="button" className={buttonClass(variant, size, className)} {...props} />
}

export function Card({
  className,
  highlighted = false,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement> & { highlighted?: boolean }) {
  return (
    <section
      className={cn(
        'rounded-lg border bg-white transition-shadow dark:bg-zinc-900',
        highlighted
          ? 'border-blue-500 ring-2 ring-blue-500/30'
          : 'border-zinc-200 dark:border-zinc-800',
        className,
      )}
      {...props}
    >
      {children}
    </section>
  )
}

export function CardTitle({ children, className }: { children: ReactNode; className?: string }) {
  return <h2 className={cn('text-sm font-semibold', className)}>{children}</h2>
}

const TONE = {
  amber:
    'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/30',
  rose: 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:ring-rose-500/30',
  emerald:
    'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/30',
  zinc: 'bg-zinc-100 text-zinc-600 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:ring-zinc-700',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/30',
}

export type Tone = keyof typeof TONE

export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1',
        TONE[tone],
      )}
    >
      {children}
    </span>
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
      className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300"
    >
      {message}
    </div>
  )
}

export function Spinner({ label, className }: { label: string; className?: string }) {
  return (
    <div className={cn('flex items-center gap-2 text-sm text-zinc-500', className)} role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  )
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium">{label}</span>
      <span className="mt-1.5 block">{children}</span>
      {hint && <span className="mt-1.5 block text-xs text-zinc-500">{hint}</span>}
    </label>
  )
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(inputClass, className)} {...props} />
}

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <svg
        className="size-6 text-blue-600 dark:text-blue-500"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden
      >
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="5" opacity=".5" />
        <path d="M12 12 18 6" strokeLinecap="round" />
      </svg>
      <span className="text-sm font-semibold tracking-tight">Release Radar</span>
    </div>
  )
}

export function GitHubIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden {...props}>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}

export function Avatar({
  name,
  url,
  className,
}: {
  name: string
  url?: string | null
  className?: string
}) {
  const initials = name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return url ? (
    <img src={url} alt="" className={cn('size-7 rounded-full', className)} />
  ) : (
    <span
      className={cn(
        'grid size-7 place-items-center rounded-full bg-zinc-200 text-xs font-medium dark:bg-zinc-800',
        className,
      )}
    >
      {initials}
    </span>
  )
}
