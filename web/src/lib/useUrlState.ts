import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

/** State mirrored into the query string, so a dashboard view can be shared or reloaded. */
export function useUrlState<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams()
  const state = { ...defaults }
  for (const key of Object.keys(defaults) as (keyof T & string)[]) {
    const value = params.get(key)
    if (value !== null) state[key] = value as T[typeof key]
  }

  const setState = useCallback(
    (patch: Partial<T>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          for (const [key, value] of Object.entries(patch)) {
            if (value) next.set(key, value)
            else next.delete(key)
          }
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  return [state, setState] as const
}
