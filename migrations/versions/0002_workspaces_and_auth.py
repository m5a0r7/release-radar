"""workspaces, users and sessions; release target dates

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12 23:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_table(
        "identities",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(128), nullable=False),
        sa.Column("login", sa.String(255), nullable=True),
        sa.UniqueConstraint("provider", "subject", name="uq_identities_provider_subject"),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column(
            "workspace_id",
            sa.BigInteger(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Projects created before workspaces existed move into one workspace with no members;
    # the first user to sign in becomes its owner.
    op.add_column("projects", sa.Column("workspace_id", sa.BigInteger(), nullable=True))
    op.execute(
        """
        WITH orphan AS (
            INSERT INTO workspaces (name)
            SELECT 'Imported projects' WHERE EXISTS (SELECT 1 FROM projects)
            RETURNING id
        )
        UPDATE projects SET workspace_id = (SELECT id FROM orphan)
        """
    )
    op.alter_column("projects", "workspace_id", nullable=False)
    op.create_foreign_key(
        "fk_projects_workspace_id_workspaces",
        "projects",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_projects_slug", "projects", type_="unique")
    op.drop_constraint("uq_projects_tracker_key", "projects", type_="unique")
    op.create_unique_constraint("uq_projects_workspace_slug", "projects", ["workspace_id", "slug"])
    op.create_unique_constraint(
        "uq_projects_workspace_tracker_key", "projects", ["workspace_id", "tracker", "tracker_key"]
    )

    op.add_column("releases", sa.Column("target_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("releases", "target_date")
    op.drop_constraint("uq_projects_workspace_tracker_key", "projects", type_="unique")
    op.drop_constraint("uq_projects_workspace_slug", "projects", type_="unique")
    op.create_unique_constraint("uq_projects_tracker_key", "projects", ["tracker", "tracker_key"])
    op.create_unique_constraint("uq_projects_slug", "projects", ["slug"])
    op.drop_constraint("fk_projects_workspace_id_workspaces", "projects", type_="foreignkey")
    op.drop_column("projects", "workspace_id")
    op.drop_table("sessions")
    op.drop_index("ix_memberships_user_id", "memberships")
    op.drop_table("memberships")
    op.drop_table("workspaces")
    op.drop_table("identities")
    op.drop_table("users")
