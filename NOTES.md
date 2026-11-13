# Notes

## How to run it

See the [README quickstart](README.md#60-second-quickstart): `cp .env.example .env`,
`docker compose up --build -d`, then open <http://localhost:8080> or use the `curl` commands. Optional env vars: `GITHUB_TOKEN`
(no scopes needed), `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.

## Architecture

```
 web (nginx) ┌──────── api (FastAPI) ────────┐            ┌──── worker ────┐
 React UI ──►│ /auth /me /connect /projects  │── jobs ──► │ claim (SKIP    │──► Jira REST
             │ /syncs /drift /narrative      │  (Postgres)│ LOCKED), sync, │──► GitHub REST
             └──────┬───────────────▲────────┘            │ re-queue (6 h) │
                    │ read          │ evidence → Claude   └───────┬────────┘
                    ▼               │ → verify → calibrate        ▼ upsert pages
                 Postgres: users, identities, workspaces, memberships, sessions,
                           projects, releases, work_items, work_item_events,
                           code_changes, sync_cursors, jobs, narratives, llm_calls
```

Reads never call upstream APIs. A `POST .../syncs` writes a job row; a separate worker process
claims it with `FOR UPDATE SKIP LOCKED` under a lease, pulls the release's tickets (Jira JQL
`fixVersion WAS <id>`, so tickets later moved out are included) and the repository's PRs, and
upserts them page by page. A sync cursor per stream makes re-syncs incremental, and upserts make
them idempotent. Tickets are stored with their append-only change history, which is what lets
`insights/timeline.py` rebuild membership and resolution as of any date. The drift metrics in
`insights/drift.py` are pure functions over that history, so they are unit-tested without a
database. Connectors implement two small protocols (`WorkTracker`, `CodeHost`), so adding Linear
or Azure DevOps is one new class.

GitHub Issues is a second `WorkTracker`: milestones are releases, issues in a milestone are its
scope, and the issue event log (`milestoned`, `demilestoned`, `closed`, `reopened`, `assigned`)
maps onto the same normalized history as Jira's changelog, so the metrics have no
tracker-specific code. Issues moved out of a milestone no longer appear under it, so the sync also
scans the repository's recent `demilestoned` events to count removals. PRs link to issues by `#123`
in the title or description; for Jira only the title is used, as before.

The narrative pipeline treats the LLM as an explainer, not a calculator:

1. `insights/evidence.py` flattens the report into numbered facts (`E1`, `E2`, …) with units and
   the ticket keys behind them.
2. Claude is forced to answer through a tool call whose JSON schema starts with an `analysis`
   scratchpad, so it reasons before it writes. The scratchpad is never returned.
3. `narrative/verifier.py` rejects any cited evidence id, number, date or ticket key that is not
   in the evidence. On failure the model gets one repair attempt with the exact errors.
4. `narrative/confidence.py` caps the model's confidence by sample size, number of weeks and data
   coverage; the response shows both the model's and the calibrated value.
5. If the LLM fails or is not configured, a deterministic template narrator restates the
   evidence and the response is marked `degraded`. Only good LLM results are cached, keyed on a
   hash of the evidence, prompt version and model.

The dashboard (`web/`) is a static React app. Nginx serves it and proxies `/v1` to the API, so
the browser talks to one origin and the API needs no CORS. Its TypeScript types are generated
from the API's OpenAPI schema, so a backend change that breaks the UI fails type-checking in CI.
Evidence chips in the narrative link back to the dashboard tile that shows the same number.

Accounts: GitHub OAuth (authorization-code flow, no scopes) creates a user, an identity and a
personal workspace on first sign-in; every project belongs to a workspace and every project route
filters by the caller's workspace. Sessions are random tokens stored as SHA-256 hashes, sent as an
httpOnly `SameSite=Lax` cookie, which together with JSON-only write endpoints is the CSRF defence.
The connect wizard calls `/v1/connect/*`, the one place where a request (not the worker) talks to
Jira and GitHub, so a user learns before the first sync whether the key exists and whether the
repository's PRs mention its tickets at all.

## Main decisions and trade-offs

- **Jira + GitHub, public Apache data.** This matches what Loop does (planning data plus delivery
  signals) and needs no credentials from reviewers. Apache projects put the Jira key in PR
  titles, which gives exact ticket↔PR links without guessing.
- **Polling, not webhooks.** Webhooks need admin rights on the source projects and a public URL.
  Polling and a future webhook receiver would feed the same upsert path.
- **Postgres as the job queue.** It gives durable jobs, leases, retries and one-active-sync-per-
  release (a partial unique index) without adding Redis or Celery. At much higher volume I would
  move to a dedicated queue.
- **The LLM never sees ticket titles or descriptions.** It sees only computed evidence and ticket
  keys, which keeps the prompt-injection surface small. The cost is that it cannot explain *what*
  the work was about.
- **Bounded LLM cost.** The prompt is aggregated evidence, so its size does not grow with ticket
  count. A token budget trims it further for very long periods, a per-process semaphore caps
  concurrent calls, and a per-workspace ledger (`llm_calls`) enforces hourly request and daily
  token quotas. The quota check reserves a row under a per-workspace advisory lock, so two
  concurrent requests cannot both spend the last unit. The ledger uses its own short transactions
  so it never holds the request's transaction open across the LLM call.
- **GitHub Issues costs one request per issue for its history.** The issues list has no event
  data, so a first sync of a 2,000-issue milestone is about 2,000 requests (40% of an hourly token
  quota); later syncs only fetch issues updated since the last one. The sync item cap bounds it.
- **Security.** Upstream base URLs come only from configuration; project keys, release ids and
  repository names are validated against strict patterns before they reach JQL or URLs; GitHub
  pagination links are only followed back to the configured host; tokens are `SecretStr`, blank
  values count as unset, and access logs record the path only, never query strings.
- **Metric limits.** "Unplanned" is a heuristic (added within 24h of resolution). Throughput is
  counted in tickets, not effort, because Kafka tickets carry no estimates. The forecast assumes
  future weeks look like the observed ones.

- **Vite + React instead of Next.js.** The dashboard has no SEO needs and the API already
  exists, so a static app behind Nginx is enough; Next.js would add a Node server for no gain.
- **Own sessions instead of JWTs.** Server-side sessions can be revoked on sign-out and need no
  key rotation; the cost is one indexed lookup per request.
- **Workspaces from day one.** Even with one member each, scoping every query by workspace now
  is far cheaper than retrofitting tenancy later. Inviting teammates is the missing piece.
- **Devcontainer is optional.** It gives a one-click setup with Postgres and the test database,
  but everything also runs with uv, pnpm and `docker compose up -d db` on the host.

## What I'd do next with another day

- Workspace invitations and roles, and a workspace switcher (the data model already supports
  several memberships per user).
- Connecting private repositories and Jira Cloud sites per workspace (GitHub App installation and
  Atlassian OAuth), instead of one server-wide Jira and public GitHub data.
- A webhook receiver next to the 6-hourly re-sync.
- Acting on the suggestion ("move 12 idle tickets to 4.6.0") after the user approves it.
- An eval suite of synthetic drift scenarios with planted causes, run against the real model
  on prompt changes, to measure hypothesis accuracy and calibration.
- Prometheus metrics (request latency, job outcomes, LLM tokens from `llm_calls` and verifier
  failure rate), and per-workspace quota overrides for paying customers.
- GitHub Issues via the GraphQL API (one query per page of issues with their timelines, instead of
  one request per issue), and a Linear connector, and Bedrock as an LLM provider (`AsyncAnthropicBedrock` is a drop-in swap).

## How I used AI

I used Cursor's agent throughout: to explore the Jira and GitHub APIs (for example, checking that
`fixVersion WAS` works and that Kafka tags releases at resolution), to scaffold modules, and to
write tests. I reviewed every file and changed several things it got wrong at first, such as a
forecast that moved in whole weeks and an `.env` template whose blank token would have been sent
to GitHub as an empty bearer token.
