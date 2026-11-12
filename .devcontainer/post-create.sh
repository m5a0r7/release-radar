#!/usr/bin/env bash
set -euo pipefail

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Named volumes are created root-owned.
sudo chown -R "$(id -u):$(id -g)" "$UV_PROJECT_ENVIRONMENT" web/node_modules

uv sync --locked
(cd web && pnpm install --frozen-lockfile)
[ -f .env ] || cp .env.example .env

uv run python .devcontainer/create_test_db.py
uv run alembic upgrade head

echo "Ready. Run 'make api', 'make worker' and 'make web' in separate terminals."
