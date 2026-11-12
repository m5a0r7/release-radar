import { useState, type FormEvent } from 'react'

import { useCreateProject } from '../api/hooks'
import { Button, Card, ErrorNotice, Field, inputClass } from './ui'

export function AddProjectForm({ onCreated }: { onCreated: (slug: string) => void }) {
  const [slug, setSlug] = useState('kafka')
  const [key, setKey] = useState('KAFKA')
  const [repository, setRepository] = useState('apache/kafka')
  const create = useCreateProject()

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      { slug, tracker_key: key, ...(repository ? { repository } : {}) },
      { onSuccess: (project) => onCreated(project.slug) },
    )
  }

  return (
    <Card title="Track a project" className="mx-auto max-w-xl">
      <p className="mb-4 text-sm text-slate-500">
        Connect a public Jira project and, optionally, the GitHub repository whose pull requests
        reference its tickets.
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <Field label="Name">
          <input
            className={inputClass}
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
          />
        </Field>
        <Field label="Jira project key">
          <input
            className={inputClass}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            required
          />
        </Field>
        <Field label="GitHub repository">
          <input
            className={inputClass}
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
            placeholder="owner/name"
          />
        </Field>
        <div className="sm:col-span-3">
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? 'Connecting…' : 'Track project'}
          </Button>
        </div>
      </form>
      {create.error && (
        <div className="mt-4">
          <ErrorNotice error={create.error} />
        </div>
      )}
    </Card>
  )
}
