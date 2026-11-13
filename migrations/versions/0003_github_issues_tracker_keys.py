"""GitHub Issues tracker keys (`owner/name`)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13 02:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("projects", "tracker_key", type_=sa.String(140), existing_nullable=False)


def downgrade() -> None:
    # Fails if a GitHub project's key no longer fits; remove those projects first.
    op.alter_column("projects", "tracker_key", type_=sa.String(32), existing_nullable=False)
