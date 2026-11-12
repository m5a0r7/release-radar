import type { DriftReport } from '../../api/client'
import { itemUrl, percent, searchUrl } from '../../lib/format'
import { Card, CardTitle } from '../ui'

const SHOWN = 6

export function AttentionCard({
  report,
  itemTemplate,
  searchTemplate,
  highlighted,
}: {
  report: DriftReport
  itemTemplate: string
  searchTemplate: string
  highlighted: boolean
}) {
  const { attention, code } = report
  const shown = attention.items.slice(0, SHOWN)

  return (
    <Card
      data-sections="code"
      highlighted={highlighted}
      className="flex flex-col p-5 xl:col-span-2"
    >
      <div className="flex items-baseline justify-between">
        <CardTitle>Needs attention</CardTitle>
        {attention.total > 0 && (
          <span className="num text-xs text-zinc-400">{attention.total}</span>
        )}
      </div>
      {shown.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500">
          Nothing stands out: no idle tickets and no merged work left open.
        </p>
      ) : (
        <ul className="mt-3 space-y-3 text-sm">
          {shown.map((item) => (
            <li key={item.key} className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-baseline gap-2">
                  <a
                    href={itemUrl(itemTemplate, item.key)}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="shrink-0 font-mono text-xs text-zinc-500 hover:text-blue-600 hover:underline"
                  >
                    {item.key}
                  </a>
                  <span className="shrink-0">
                    {item.reason === 'merged_not_resolved' ? 'Done in code, open in Jira' : 'Idle'}
                  </span>
                </p>
                {item.title && (
                  <p className="truncate text-xs text-zinc-400" title={item.title}>
                    {item.title}
                  </p>
                )}
              </div>
              <span className="num shrink-0 text-xs text-zinc-400">
                {item.reason === 'merged_not_resolved'
                  ? `PR merged ${item.days} d ago`
                  : `${item.days} days`}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-xs">
        {attention.items.length > 0 ? (
          <a
            href={searchUrl(
              searchTemplate,
              attention.items.map((i) => i.key),
            )}
            target="_blank"
            rel="noreferrer noopener"
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {attention.total > attention.items.length
              ? `View top ${attention.items.length} in Jira`
              : `View all ${attention.total} in Jira`}{' '}
            →
          </a>
        ) : (
          <span />
        )}
        <span className="text-zinc-400">
          {code.available
            ? `${percent(code.unlinked_share)} of merged PRs cite no ticket`
            : 'Connect a repository to see work done in code'}
        </span>
      </div>
    </Card>
  )
}
