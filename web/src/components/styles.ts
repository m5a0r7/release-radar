import { cn } from '../lib/cn'

const BUTTON = {
  primary:
    'bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white',
  secondary:
    'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800',
  accent: 'bg-blue-600 text-white hover:bg-blue-500',
  ghost:
    'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
  danger:
    'border border-zinc-200 bg-white text-rose-600 hover:bg-rose-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-rose-400 dark:hover:bg-rose-500/10',
}

const SIZE = { sm: 'px-2.5 py-1 text-xs', md: 'px-3 py-1.5 text-sm', lg: 'px-4 py-2.5 text-sm' }

export type ButtonVariant = keyof typeof BUTTON
export type ButtonSize = keyof typeof SIZE

export const buttonClass = (
  variant: keyof typeof BUTTON = 'primary',
  size: keyof typeof SIZE = 'md',
  className?: string,
) =>
  cn(
    'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600',
    'disabled:pointer-events-none disabled:opacity-50',
    BUTTON[variant],
    SIZE[size],
    className,
  )

export const inputClass = cn(
  'w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400',
  'focus:border-blue-600 focus:ring-2 focus:ring-blue-600/20 focus:outline-none',
  'dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100',
)
