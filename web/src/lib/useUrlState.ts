import { useCallback, useState } from 'react'

/** State mirrored into the query string, so a dashboard view can be shared or reloaded. */
export function useUrlState<T extends Record<string, string>>(defaults: T) {
  const [state, setRaw] = useState<T>(() => {
    const params = new URLSearchParams(window.location.search)
    const initial = { ...defaults }
    for (const key of Object.keys(defaults) as (keyof T & string)[]) {
      const value = params.get(key)
      if (value !== null) initial[key] = value as T[typeof key]
    }
    return initial
  })

  const setState = useCallback((patch: Partial<T>) => {
    setRaw((current) => {
      const next = { ...current, ...patch }
      const params = new URLSearchParams()
      for (const [key, value] of Object.entries(next)) if (value) params.set(key, value)
      window.history.replaceState(null, '', `?${params.toString()}`)
      return next
    })
  }, [])

  return [state, setState] as const
}
