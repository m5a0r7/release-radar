# Agent guide

Release Radar reports whether a release is drifting from its plan (Jira tickets vs GitHub PRs)
and asks an LLM to explain the numbers with cited evidence. Read `NOTES.md` for the architecture.

## Layout

- `src/radar/connectors/` — upstream clients. New sources implement `WorkTracker` or `CodeHost`
  in `base.py` and are registered in `registry.py`.
- `src/radar/jobs/` and `src/radar/ingest/` — the worker: job queue (`SKIP LOCKED` leases) and
  idempotent, incremental sync.
- `src/radar/insights/` — pure functions over ticket history. No I/O, no database.
- `src/radar/narrative/` — evidence → LLM → verifier → confidence calibration → template fallback.
- `src/radar/api/` — FastAPI routes and Pydantic schemas.
- `migrations/` — Alembic. `web/` — React + Vite + Tailwind dashboard.

## Commands

```bash
make lint test       # backend: ruff, mypy --strict, pytest (needs Postgres)
make web-check       # frontend: prettier, oxlint, vitest, build
make openapi         # after any API schema change: regenerate web/openapi.json and TS types
```

Run both checks before you finish. Postgres for tests: `docker compose up -d db`.

## Rules

- The LLM explains numbers; it never computes them. Every number a narrative may mention must
  come from `insights/evidence.py`, and `narrative/verifier.py` must be able to check it.
- A new metric needs: the computation in `insights/` with unit tests, an evidence entry, a field
  in the API schema, and a tile in the dashboard. Bump `PROMPT_VERSION` (`narrative/prompt.py`) if the prompt changes.
- Metrics are computed as of the period boundaries from change history, never from current state.
- Reads never call upstream APIs; only the worker does.
- Schema changes go through a new Alembic revision. Never edit an applied one.
- Errors are RFC 9457 problems raised as `ProblemError`.
- Frontend types come from `web/src/api/schema.d.ts` (generated). Don't hand-write API types.
- Never commit secrets. Settings come from environment variables (`config.py`, `.env.example`).
- Match the existing style: small modules, typed everything, comments only for non-obvious "why".
