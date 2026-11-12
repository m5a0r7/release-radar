"""Persistence model.

Upstream data is stored in a source-agnostic shape: any work tracker (Jira today) maps to
`WorkItem` + `WorkItemEvent`, any code host (GitHub today) maps to `CodeChange`. Events are
append-only history, so membership and status can be reconstructed as of any point in time.
"""

from datetime import date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
    }


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    tracker: Mapped[str] = mapped_column(String(32))
    tracker_key: Mapped[str] = mapped_column(String(32))
    code_host: Mapped[str | None] = mapped_column(String(32))
    repository: Mapped[str | None] = mapped_column(String(140))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (UniqueConstraint("tracker", "tracker_key", name="uq_projects_tracker_key"),)


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    released: Mapped[bool] = mapped_column(Boolean)
    archived: Mapped[bool] = mapped_column(Boolean)
    release_date: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("project_id", "external_id", name="uq_releases_project_external"),
        UniqueConstraint("project_id", "name", name="uq_releases_project_name"),
    )


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64))
    status_category: Mapped[str] = mapped_column(String(16))
    priority: Mapped[str | None] = mapped_column(String(64))
    assignee: Mapped[str | None] = mapped_column(String(255))
    release_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("project_id", "external_id", name="uq_work_items_project_external"),
        UniqueConstraint("project_id", "key", name="uq_work_items_project_key"),
        Index("ix_work_items_release_ids", "release_ids", postgresql_using="gin"),
    )


class WorkItemEvent(Base):
    __tablename__ = "work_item_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[datetime]
    field: Mapped[str] = mapped_column(String(32))
    from_value: Mapped[str | None] = mapped_column(String(255))
    to_value: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("work_item_id", "external_id", name="uq_work_item_events_item_external"),
        Index("ix_work_item_events_item_occurred", "work_item_id", "occurred_at"),
        Index("ix_work_item_events_field_to", "field", "to_value"),
        Index("ix_work_item_events_field_from", "field", "from_value"),
    )


class CodeChange(Base):
    __tablename__ = "code_changes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(64))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(16))
    url: Mapped[str] = mapped_column(String(512))
    linked_keys: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    merged_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("project_id", "external_id", name="uq_code_changes_project_external"),
        Index("ix_code_changes_project_merged", "project_id", "merged_at"),
        Index("ix_code_changes_linked_keys", "linked_keys", postgresql_using="gin"),
    )


class SyncCursor(Base):
    """High-water mark per upstream stream, so re-syncs fetch only what changed."""

    __tablename__ = "sync_cursors"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    stream: Mapped[str] = mapped_column(String(128), primary_key=True)
    synced_until: Mapped[datetime]
    synced_from: Mapped[datetime | None]


class Job(Base):
    """Durable job queue row, claimed by workers with `FOR UPDATE SKIP LOCKED`."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    payload: Mapped[dict[str, Any]]
    dedupe_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_after: Mapped[datetime] = mapped_column(server_default=func.now())
    lease_expires_at: Mapped[datetime | None]
    progress: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    __table_args__ = (
        Index(
            "uq_jobs_active_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_jobs_claimable", "status", "run_after"),
    )


class Narrative(Base):
    """Cached LLM output keyed by a hash of its exact inputs (evidence, prompt, model)."""

    __tablename__ = "narratives"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
