# Release Radar

Release Radar checks whether a software release is drifting from its plan. It reads tickets from
Jira and pull requests from GitHub, rebuilds what the release looked like on any date, and reports
scope change, unplanned work, idle tickets, code/ticket status lag and a forecast finish date.
A second endpoint asks an LLM (Claude) to explain the numbers: findings, a root-cause hypothesis,
a calibrated confidence score, and an evidence chain that points back to each number.

A dashboard (React, TypeScript, Tailwind) shows the same numbers and lets you click any piece of
evidence in the explanation to jump to the metric it came from.

The demo uses public data (Apache Kafka's Jira and `apache/kafka` on GitHub), so no credentials
are required.

## 60-second quickstart

Prerequisites: Docker with Compose v2.

```bash
cp .env.example .env            # optional: add GITHUB_TOKEN and ANTHROPIC_API_KEY
docker compose up --build -d    # postgres, migrations, api, worker, web
```

Open the dashboard at <http://localhost:8080>, track `KAFKA` / `apache/kafka`, pick release
`4.5.0`, press **Sync now**, then **Explain with AI**. The same flow over the API:

```bash

# 1. Track a project (fetches its releases from Jira)
curl -s -X POST localhost:8000/v1/projects -H 'content-type: application/json' \
  -d '{"slug":"kafka","tracker_key":"KAFKA","repository":"apache/kafka"}'

# 2. Sync a release in the background (202 + Location of the job)
curl -s -X POST localhost:8000/v1/projects/kafka/releases/4.5.0/syncs
curl -s localhost:8000/v1/jobs/1            # poll until "status": "succeeded" (~30s)

# 3. Insight: plan-vs-actual metrics for the last 8 weeks
curl -s "localhost:8000/v1/projects/kafka/releases/4.5.0/drift?target_date=2026-12-15"

# 4. Narrative: LLM explanation with hypothesis, confidence and evidence
curl -s "localhost:8000/v1/projects/kafka/releases/4.5.0/narrative?target_date=2026-12-15"
```

Interactive API docs: <http://localhost:8000/docs>.

Without `ANTHROPIC_API_KEY` the narrative uses the deterministic `template` provider. To use
Claude, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`, then
`docker compose up -d`. Without `GITHUB_TOKEN`, GitHub allows 60 requests/hour, which is enough
for one 120-day sync of `apache/kafka`; a token with no scopes raises it to 5,000.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/projects` | Track a Jira project, optionally linked to a GitHub repository. `201`, `409` if it exists, `422` if Jira does not know the key. |
| `GET` | `/v1/projects`, `/v1/projects/{slug}` | List or read tracked projects. |
| `GET` | `/v1/projects/{slug}/releases` | Releases (`?released=false`, `?include_archived=true`, `?limit=`). |
| `POST` | `/v1/projects/{slug}/releases/{release}/syncs` | Queue a sync. `202` with `Location: /v1/jobs/{id}`; `409` if one is already queued or running. |
| `GET` | `/v1/jobs/{id}` | Job status, attempts, progress and last error. |
| `GET` | `/v1/projects/{slug}/releases/{release}/drift` | Drift metrics over a period. |
| `GET` | `/v1/projects/{slug}/releases/{release}/narrative` | LLM narrative over the same period (`?refresh=true` bypasses the cache). |
| `GET` | `/healthz`, `/readyz` | Liveness, and readiness (checks the database). |

Insight endpoints accept `from` and `to` (inclusive UTC dates; default: the last 56 days ending
today, max 366 days) and `target_date` (defaults to the release date in Jira). They return `ETag`
and honour `If-None-Match` with `304`. Every error is `application/problem+json` (RFC 9457) and
carries the request's `X-Request-ID`.

## What the metrics mean

All metrics are computed as of the period boundaries from each ticket's change history, not from
its current state, so a past period gives the same answer it would have given at the time.

| Metric | Definition | Why it matters |
|---|---|---|
| `scope` | Tickets in the release at the start and end of the period, plus how many were added and removed in between. | Scope churn is the most common reason a date slips. |
| `progress` | Tickets resolved in the period, compared with the previous period of equal length. | Shows whether the team is speeding up or slowing down. |
| `planning.unplanned_share` | Share of completed tickets that were only added to the release within 24h of being resolved. | Shows how much of the work the plan never contained. Kafka tags most tickets at resolution, which makes its plan a poor predictor. |
| `idle` | Open tickets with no ticket activity and no linked-PR activity for 14+ days. | Idle tickets are candidates to move to a later release. |
| `throughput` | Tickets resolved per week. Unusual weeks are flagged with a modified z-score (median and MAD; at least 6 weeks; threshold 3.5). | Separates real problems from normal week-to-week noise. |
| `forecast` | Monte Carlo: 2,000 simulations that replay the observed weekly throughput to estimate P50/P85 finish dates and the probability of meeting `target_date`. Seeded, so the same inputs give the same output. | Turns "behind" into "how likely we are to ship on time". |
| `code` | PRs merged in the period that reference release tickets, PRs that reference no ticket at all (`unlinked_share`), and open tickets whose PR is already merged (status lag). | Cross-checks the tracker against the code. |
| `coverage` | Whether synced data covers the whole period, with notes when it does not. | Missing data shows up in the response instead of being hidden. |

`status` is `on_track` / `at_risk` / `off_track` from the on-time probability when a target date
exists (≥70% / ≥40% / below), otherwise from scope churn above 25% and idle share above 30%.

## Developing

**Devcontainer (recommended).** Open the folder in VS Code or Cursor and choose *Reopen in
Container*. It starts Postgres, installs Python 3.12, uv, Node 22 and pnpm, installs dependencies,
creates the test database and runs migrations. Then run `make api`, `make worker` and `make web`
in three terminals and open <http://localhost:5173>.

**On your machine.** Requires Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22 with pnpm,
and Postgres 16 (`docker compose up -d db` is enough).

```bash
make install   # uv sync + pnpm install
make migrate
make api       # terminal 1, http://localhost:8000
make worker    # terminal 2
make web       # terminal 3, http://localhost:5173 (proxies /v1 to the API)
```

The web client's types are generated from the API's OpenAPI schema. After changing an API schema,
run `make openapi`; CI fails if the committed schema or types are out of date.

## Tests and checks

```bash
make lint      # ruff format --check, ruff check, mypy --strict
make test      # needs Postgres; TEST_DATABASE_URL defaults to .../radar_test
make web-check # prettier, oxlint, vitest, production build
```

Integration tests run the real Alembic migrations against Postgres and mock Jira and GitHub over
HTTP. CI (`.github/workflows/ci.yml`) runs both sets of checks, the generated-types check and both
Docker builds.

See [NOTES.md](NOTES.md) for the architecture, trade-offs and next steps.
