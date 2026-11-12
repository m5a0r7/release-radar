import { itemUrl } from '../lib/format'

const SHOWN = 6

export function ItemLinks({ keys, template }: { keys: string[]; template: string }) {
  if (keys.length === 0) return null
  const hidden = keys.length - SHOWN
  return (
    <ul className="mt-3 flex flex-wrap items-center gap-1.5">
      {keys.slice(0, SHOWN).map((key) => (
        <li key={key}>
          <a
            href={itemUrl(template, key)}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded border border-zinc-200 bg-white px-1.5 py-0.5 font-mono text-[11px] text-zinc-600 hover:border-blue-300 hover:text-blue-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:text-blue-400"
          >
            {key}
          </a>
        </li>
      ))}
      {hidden > 0 && <li className="text-[11px] text-zinc-400">+{hidden} more</li>}
    </ul>
  )
}
