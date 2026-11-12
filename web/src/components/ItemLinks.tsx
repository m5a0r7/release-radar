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
            className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700 hover:bg-indigo-50 hover:text-indigo-700"
          >
            {key}
          </a>
        </li>
      ))}
      {hidden > 0 && <li className="text-[11px] text-slate-400">+{hidden} more</li>}
    </ul>
  )
}
