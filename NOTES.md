# Notes

## How to run it

See the [README quickstart](README.md#60-second-quickstart): `cp .env.example .env`,
`docker compose up --build -d`, then the `curl` commands. Optional env vars: `GITHUB_TOKEN`
(no scopes needed), `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.

## Architecture

```
          ┌──────── api (FastAPI) ────────┐            ┌──── worker ────┐
client ──►│ /projects /syncs /drift       │── jobs ──► │ claim (SKIP    │──► Jira REST
          │ /narrative                    │  (Postgres)│ LOCKED), sync  │──► GitHub REST
          └──────┬───────────────▲────────┘            └───────┬────────┘
                 │ read          │ evidence → Claude           │ upsert pages
                 ▼               │ → verify → calibrate        ▼
              Postgres: projects, releases, work_items, work_item_events,
                        code_changes, sync_cursors, jobs, narratives
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
- **Security.** Upstream base URLs come only from configuration; project keys, release ids and
  repository names are validated against strict patterns before they reach JQL or URLs; GitHub
  pagination links are only followed back to the configured host; tokens are `SecretStr`, blank
  values count as unset, and access logs record the path only, never query strings.
- **Metric limits.** "Unplanned" is a heuristic (added within 24h of resolution). Throughput is
  counted in tickets, not effort, because Kafka tickets carry no estimates. The forecast assumes
  future weeks look like the observed ones.

## What I'd do next with another day

- The small web page from the UX plan: health card, drift chart, and narrative with clickable
  evidence chips.
- A scheduler that re-syncs tracked releases every N minutes, plus a webhook receiver.
- An eval suite of synthetic drift scenarios with planted causes, run against the real model
  on prompt changes, to measure hypothesis accuracy and calibration.
- Rate limiting on the narrative endpoint, which is the expensive one, and Prometheus metrics
  (request latency, job outcomes, LLM tokens and verifier failure rate).
- A Linear connector, and Bedrock as an LLM provider (`AsyncAnthropicBedrock` is a drop-in swap).

## How I used AI

I used Cursor's agent throughout: to explore the Jira and GitHub APIs (for example, checking that
`fixVersion WAS` works and that Kafka tags releases at resolution), to scaffold modules, and to
write tests. I reviewed every file and changed several things it got wrong at first, such as a
forecast that moved in whole weeks and an `.env` template whose blank token would have been sent
to GitHub as an empty bearer token.
