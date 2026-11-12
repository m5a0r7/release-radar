import { useCallback, useSyncExternalStore } from 'react'

export type Theme = 'system' | 'light' | 'dark'

const KEY = 'theme'
const listeners = new Set<() => void>()

function read(): Theme {
  const stored = localStorage.getItem(KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

/** Mirrors public/theme.js, which applies the theme before first paint. */
function apply(theme: Theme) {
  const dark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const onSystemChange = () => apply(read())
  media.addEventListener('change', onSystemChange)
  return () => {
    listeners.delete(listener)
    media.removeEventListener('change', onSystemChange)
  }
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, read, () => 'system' as Theme)
  const setTheme = useCallback((next: Theme) => {
    if (next === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, next)
    apply(next)
    listeners.forEach((listener) => listener())
  }, [])
  return [theme, setTheme]
}
