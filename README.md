# Release Radar

Release Radar checks whether a software release is drifting from its plan. It reads tickets from
Jira or GitHub Issues and pull requests from GitHub, rebuilds what the release looked like on any date, and reports
scope change, unplanned work, idle tickets, code/ticket status lag and a forecast finish date.
A second endpoint asks an LLM (Claude) to explain the numbers: findings, a root-cause hypothesis,
a calibrated confidence score, and an evidence chain that points back to each number.

A web app (React, TypeScript, Tailwind) adds accounts and workspaces (sign in with GitHub), a
wizard that connects a Jira project (or a repository's GitHub Issues) and checks that its pull
requests actually reference its tickets, and a dashboard per release: a one-line verdict ("37% chance 4.5.0 ships by Dec 15"),
KPI tiles, a burn-up chart with the forecast and target, a "needs attention" list, and the
explanation, where every piece of evidence links back to the metric it came from. Tracked
releases re-sync in the background every 6 hours. Light and dark themes.

The demo uses public data (Apache Kafka's Jira and `apache/kafka` on GitHub), so no credentials
are required.

## 60-second quickstart

Prerequisites: Docker with Compose v2.

```bash
cp .env.example .env            # optional: add GITHUB_TOKEN and ANTHROPIC_API_KEY
docker compose up --build -d    # postgres, migrations, api, worker, web
```

Open <http://localhost:8080>, choose **Try the demo account**, then **Connect project**: Jira key
`KAFKA`, repository `apache/kafka`, release `4.5.0`, target date of your choice. The first sync
takes about 30 seconds; then press **Explain**. For GitHub Issues, pick **GitHub Issues** in the
first step and enter a repository such as `apache/arrow`: milestones become releases, and pull
requests link to issues through `#123` references in their title or description. The same flow over the API:

```bash
# 0. Sign in (the demo account; the session is an httpOnly cookie)
curl -s -c jar -X POST localhost:8000/v1/auth/demo

# 1. Track a project (fetches its releases from Jira)
curl -s -b jar -X POST localhost:8000/v1/projects -H 'content-type: application/json' \
  -d '{"slug":"kafka","tracker_key":"KAFKA","repository":"apache/kafka"}'

# 2. Set a target date, then sync the release in the background (202 + Location of the job)
curl -s -b jar -X PATCH localhost:8000/v1/projects/kafka/releases/4.5.0 \
  -H 'content-type: application/json' -d '{"target_date":"2026-12-15"}'
curl -s -b jar -X POST localhost:8000/v1/projects/kafka/releases/4.5.0/syncs
curl -s -b jar localhost:8000/v1/jobs/1     # poll until "status": "succeeded" (~30s)

# 3. Insight: plan-vs-actual metrics for the last 8 weeks
curl -s -b jar localhost:8000/v1/projects/kafka/releases/4.5.0/drift

# 4. Narrative: LLM explanation with hypothesis, confidence and evidence
curl -s -b jar localhost:8000/v1/projects/kafka/releases/4.5.0/narrative
```

Interactive API docs: <http://localhost:8000/docs>.

Without `ANTHROPIC_API_KEY` the narrative uses the deterministic `template` provider. To use
Claude, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`, then
`docker compose up -d`. Without `GITHUB_TOKEN`, GitHub allows 60 requests/hour, which is enough
for one 120-day sync of `apache/kafka`; a token with no scopes raises it to 5,000.

### Sign in with GitHub

Signing in is also signing up: the first sign-in creates the account and a personal workspace.
Each workspace sees only its own projects. To enable GitHub sign-in:

1. Create an OAuth app at <https://github.com/settings/developers> with the callback URL
   `http://localhost:8080/v1/auth/github/callback` (use `http://localhost:5173` in both places with `make web`).
2. Set `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` and `APP_BASE_URL` in `.env`.

The app asks GitHub for no scopes and discards the access token after reading the profile.
Sessions are opaque server-side tokens (only their SHA-256 is stored) in an httpOnly,
`SameSite=Lax` cookie; set `SESSION_COOKIE_SECURE=true` behind HTTPS. The demo account
(`AUTH_DEV_LOGIN`) is refused when `ENVIRONMENT=production`. Projects created before accounts
existed land in an "Imported projects" workspace that the first user to sign in adopts.

## Public demo on Railway

`.railway/railway.ts` describes the whole project: Postgres, the API (runs migrations before each deploy), the background worker, and the web app. The web app proxies `/v1` to the API over Railway's private network, so the browser still talks to one origin. The demo account stays open through `DEMO_UNTIL` (2026-12-12 in that file); after that day sign-in closes. Four always-on services will spend the $5 trial credit in roughly a week of light use, so delete the project when the review is over.

1. Sign in at [railway.com](https://railway.com) with GitHub. New accounts get $5 of credit for 30 days, with no card.
2. Install the [Railway CLI](https://docs.railway.com/guides/cli), then from this directory:

   ```bash
   railway login
   railway init          # new project; pick an empty one
   railway config apply  # creates Postgres, api, worker and web
   ```

3. In the dashboard, open the **web** service and generate a public domain. `APP_BASE_URL` on **api** is that domain, so GitHub can send people back to the site.
4. Create an OAuth app at <https://github.com/settings/developers>. Set the callback URL to `https://<the web domain>/v1/auth/github/callback`. On the **api** service, set `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET`, then redeploy **api**. The login page then shows **Continue with GitHub**, and the first sign-in creates the account.
5. On **api** and **worker**, set `GITHUB_TOKEN` (a token with no scopes). Without it GitHub allows 60 requests an hour, which a sync uses up. To turn on live explanations, also set `ANTHROPIC_API_KEY` on **api** and change `LLM_PROVIDER` to `anthropic`.
6. Open the web URL. **Try the demo account** stays available through the date on the login page.

The file deploys the private repo `m5a0r7/release-radar`, branch `main`. Grant the [Railway GitHub App](https://github.com/apps/railway-app/installations/new) access to that repo before `railway config apply`.

## API

Everything except `/v1/auth/*` and the health checks needs a session (`401` otherwise) and is
scoped to the caller's workspace (another workspace's project is a `404`).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/auth/config` | Which sign-in methods are enabled. |
| `GET` | `/v1/auth/github/login`, `/v1/auth/github/callback` | GitHub OAuth (state cookie, same-app `?next=` only). |
| `POST` | `/v1/auth/demo`, `/v1/auth/logout` | Demo sign-in (development only); sign out. |
| `GET` | `/v1/me` | The signed-in user and workspace. |
| `POST` | `/v1/connect/tracker` | Check a tracker project (`tracker`: `jira` with a key like `KAFKA`, or `github` with `owner/name`): name, upcoming releases, whether it is already connected. |
| `POST` | `/v1/connect/code` | Sample a repository's last 100 PRs and report how many reference the tracker's tickets. |
| `GET` | `/v1/connect/repositories?q=` | Search public GitHub repositories (`owner/name` searches one owner). |
| `POST` | `/v1/projects` | Track a Jira project or GitHub Issues repository, optionally linked to a GitHub code repository. `201`, `409` if the workspace already has that name or key, `422` if the tracker does not know the key. |
| `GET` | `/v1/projects`, `/v1/projects/{slug}` | List or read projects, with each tracked release's last sync. |
| `DELETE` | `/v1/projects/{slug}` | Remove a project and its synced data. |
| `GET` | `/v1/projects/{slug}/releases` | Releases (`?released=false`, `?include_archived=true`, `?limit=`). |
| `PATCH` | `/v1/projects/{slug}/releases/{release}` | Set the release's target date (`null` falls back to Jira's release date). |
| `POST` | `/v1/projects/{slug}/releases/{release}/syncs` | Queue a sync. `202` with `Location: /v1/jobs/{id}`; `409` if one is already queued or running. |
| `GET` | `/v1/jobs/{id}` | Job status, attempts, progress and last error. |
| `GET` | `/v1/projects/{slug}/releases/{release}/drift` | Drift metrics over a period. |
| `GET` | `/v1/projects/{slug}/releases/{release}/narrative` | LLM narrative over the same period (`?refresh=true` bypasses the cache). `429` with `Retry-After` when the workspace is over its AI quota. |
| `GET` | `/healthz`, `/readyz` | Liveness, and readiness (checks the database). |

Insight endpoints accept `from` and `to` (inclusive UTC dates; default: the last 56 days ending
today, max 366 days) and `target_date` (defaults to the saved target, then the release date in
Jira). They return `ETag`
and honour `If-None-Match` with `304`. Every error is `application/problem+json` (RFC 9457) and
carries the request's `X-Request-ID`.

## Limits

Each limit is an environment variable (see `.env.example`), so a large release degrades in a
predictable way instead of failing late.

| Limit | Default | When exceeded |
|---|---|---|
| `LLM_MAX_INPUT_TOKENS` | 12,000 | Evidence is trimmed in order (fewer example keys, then only the last 12 weeks plus anomalous weeks, then no keys) and a caveat says so; if it still does not fit, the template narrator answers. |
| `LLM_MAX_CONCURRENCY` | 4 per API process | Further requests wait up to 30 s, then get the template narrative. |
| `LLM_REQUESTS_PER_HOUR`, `LLM_TOKENS_PER_DAY` | 30, 1,000,000 per workspace | `429` with `Retry-After`. Every call is logged in `llm_calls` with its token counts. |
| `SYNC_MAX_WORK_ITEMS` | 20,000 per sync | The job fails with a clear error and is not retried. |
| Period | 366 days | `422`. |

The prompt does not grow with the number of tickets: evidence is aggregated (counts, rates and at
most 10 example keys per fact), so only the weekly throughput series grows with the period.

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
| `burnup` | Scope and done counts at the period start and at the end of each week. | The chart behind "is the gap closing?". |
| `attention` | Open tickets whose PR is merged (oldest merge first), then idle tickets (longest idle first); up to 25. | The concrete list to act on. |
| `coverage` | Whether synced data covers the whole period (allowing for the 6-hour background sync), with notes when it does not. | Missing data shows up in the response instead of being hidden. |

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
