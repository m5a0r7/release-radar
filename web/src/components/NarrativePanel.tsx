import { Sparkles } from 'lucide-react'

import type { Evidence, Narrative } from '../api/client'
import { percent, searchUrl, sectionOf } from '../lib/format'
import { ItemLinks } from './ItemLinks'
import { buttonClass } from './styles'
import { Button, Card, CardTitle, ErrorNotice, Spinner } from './ui'

type Props = {
  narrative: Narrative | undefined
  loading: boolean
  error: unknown
  requested: boolean
  onExplain: () => void
  onEvidence: (section: string) => void
  itemUrlTemplate: string
  searchUrlTemplate: string
}

export function NarrativePanel(props: Props) {
  const { narrative, loading, error, requested, onExplain } = props

  return (
    <Card id="narrative" className="p-5">
      <div className="flex items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-4 text-blue-600 dark:text-blue-500" aria-hidden />
          Why it is drifting
        </CardTitle>
        {narrative && (
          <span className="text-xs text-zinc-400">
            {narrative.meta.degraded
              ? 'template summary'
              : `${narrative.meta.model} · every number verified`}
            {narrative.meta.cached && ' · cached'}
          </span>
        )}
      </div>
      {!requested && !narrative && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-4">
          <p className="max-w-xl text-sm text-zinc-500">
            Ask the model to explain these numbers. Every claim cites the evidence it rests on, and
            confidence is capped by how much data there is.
          </p>
          <Button variant="accent" onClick={onExplain}>
            <Sparkles className="size-4" />
            Explain with AI
          </Button>
        </div>
      )}
      {loading && <Spinner label="Analysing the evidence…" className="mt-4" />}
      {error !== null && error !== undefined && (
        <div className="mt-4">
          <ErrorNotice error={error} />
        </div>
      )}
      {narrative && <NarrativeBody {...props} narrative={narrative} />}
    </Card>
  )
}

function NarrativeBody({
  narrative,
  onEvidence,
  itemUrlTemplate,
  searchUrlTemplate,
}: Props & { narrative: Narrative }) {
  const recommendation = narrative.recommendation
  return (
    <div className="mt-4">
      <p className="text-sm text-zinc-700 dark:text-zinc-300">{narrative.summary}</p>

      <ol className="mt-2">
        {narrative.findings.map((finding, index) => (
          <li
            key={index}
            className="border-t border-zinc-100 py-4 first:border-0 dark:border-zinc-800"
          >
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-medium">{finding.claim}</p>
              <Confidence value={finding.confidence} model={finding.model_confidence} />
            </div>
            {finding.hypothesis && (
              <p className="mt-1 text-sm text-zinc-500">
                <span className="font-medium text-zinc-600 dark:text-zinc-400">Likely cause: </span>
                {finding.hypothesis}
              </p>
            )}
            <EvidenceChips evidence={finding.evidence} onSelect={onEvidence} />
          </li>
        ))}
      </ol>

      {recommendation && (
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4 rounded-md bg-zinc-50 p-4 dark:bg-zinc-800/50">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium tracking-wider text-zinc-500 uppercase">
              Suggested · needs your approval
            </p>
            <p className="mt-1 text-sm font-medium">{recommendation.action}</p>
            <p className="mt-1 text-sm text-zinc-500">{recommendation.rationale}</p>
            <ItemLinks keys={recommendation.item_keys} template={itemUrlTemplate} />
            <EvidenceChips evidence={recommendation.evidence} onSelect={onEvidence} />
          </div>
          {recommendation.item_keys.length > 0 && (
            <a
              href={searchUrl(searchUrlTemplate, recommendation.item_keys)}
              target="_blank"
              rel="noreferrer noopener"
              className={buttonClass('primary')}
            >
              Review in Jira
            </a>
          )}
        </div>
      )}

      {narrative.caveats.length > 0 && (
        <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-zinc-500">
          {narrative.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      )}

      {narrative.meta.degraded && (
        <p className="mt-3 text-xs text-zinc-400">
          The model was unavailable or failed verification, so this is a template summary built only
          from the evidence.
        </p>
      )}
    </div>
  )
}

function EvidenceChips({
  evidence,
  onSelect,
}: {
  evidence: Evidence[]
  onSelect: (section: string) => void
}) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {evidence.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => onSelect(sectionOf(item.metric))}
          title={`${item.description}: show on the dashboard`}
          className="rounded border border-zinc-200 px-1.5 py-0.5 text-[11px] text-zinc-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-blue-500/10 dark:hover:text-blue-400"
        >
          <span className="font-semibold">{item.id}</span> {item.description}{' '}
          <span className="num font-mono">
            {String(item.value)}
            {item.unit === '%' ? '%' : ''}
          </span>
        </button>
      ))}
    </div>
  )
}

function Confidence({ value, model }: { value: number; model: number }) {
  const capped = value < model
  return (
    <div
      className="w-24 shrink-0 text-right"
      title={capped ? `Model said ${percent(model)}; capped by the amount of data.` : undefined}
    >
      <p className="num text-xs text-zinc-500">
        {percent(value)} conf.
        {capped && <span className="ml-1 text-zinc-400">(capped)</span>}
      </p>
      <div className="mt-1 h-1 rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div
          className="h-1 rounded-full bg-zinc-900 dark:bg-zinc-100"
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
    </div>
  )
}
