"""Idempotent writes of connector records. Re-running a sync never duplicates data."""

from collections.abc import Sequence
from datetime import datetime
from itertools import batched
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from radar.connectors.base import CodeChangeRecord, ReleaseRecord, WorkItemRecord
from radar.db.models import CodeChange, Release, SyncCursor, WorkItem, WorkItemEvent
from radar.ingest.linking import extract_item_keys, linking_text

EVENT_BATCH = 1000


async def upsert_releases(
    session: AsyncSession, project_id: int, records: Sequence[ReleaseRecord]
) -> None:
    if not records:
        return
    stmt = insert(Release).values(
        [
            {
                "project_id": project_id,
                "external_id": r.external_id,
                "name": r.name,
                "released": r.released,
                "archived": r.archived,
                "release_date": r.release_date,
            }
            for r in records
        ]
    )
    await session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_releases_project_external",
            set_=_excluded(stmt, "name", "released", "archived", "release_date"),
        )
    )


async def upsert_work_items(
    session: AsyncSession, project_id: int, records: Sequence[WorkItemRecord]
) -> None:
    if not records:
        return
    stmt = insert(WorkItem).values(
        [
            {
                "project_id": project_id,
                "external_id": r.external_id,
                "key": r.key,
                "title": r.title,
                "item_type": r.item_type,
                "status": r.status,
                "status_category": r.status_category.value,
                "priority": r.priority,
                "assignee": r.assignee,
                "release_ids": list(r.release_ids),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "resolved_at": r.resolved_at,
            }
            for r in records
        ]
    )
    upsert = stmt.on_conflict_do_update(
        constraint="uq_work_items_project_external",
        set_=_excluded(
            stmt,
            "key",
            "title",
            "item_type",
            "status",
            "status_category",
            "priority",
            "assignee",
            "release_ids",
            "updated_at",
            "resolved_at",
        ),
    ).returning(WorkItem.id, WorkItem.external_id)
    ids = {external_id: item_id for item_id, external_id in await session.execute(upsert)}

    events = (
        {
            "work_item_id": ids[r.external_id],
            "external_id": e.external_id,
            "occurred_at": e.occurred_at,
            "field": e.field.value,
            "from_value": e.from_value,
            "to_value": e.to_value,
        }
        for r in records
        for e in r.events
    )
    for batch in batched(events, EVENT_BATCH):
        await session.execute(
            insert(WorkItemEvent)
            .values(list(batch))
            .on_conflict_do_nothing(constraint="uq_work_item_events_item_external")
        )


async def upsert_code_changes(
    session: AsyncSession,
    project_id: int,
    project_key: str,
    records: Sequence[CodeChangeRecord],
    tracker: str = "jira",
) -> None:
    if not records:
        return
    stmt = insert(CodeChange).values(
        [
            {
                "project_id": project_id,
                "external_id": r.external_id,
                "number": r.number,
                "title": r.title,
                "author": r.author,
                "state": r.state.value,
                "url": r.url,
                "linked_keys": extract_item_keys(
                    linking_text(r.title, r.body, tracker), project_key, tracker
                ),
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "merged_at": r.merged_at,
                "closed_at": r.closed_at,
            }
            for r in records
        ]
    )
    await session.execute(
        stmt.on_conflict_do_update(
            constraint="uq_code_changes_project_external",
            set_=_excluded(
                stmt,
                "title",
                "author",
                "state",
                "linked_keys",
                "updated_at",
                "merged_at",
                "closed_at",
            ),
        )
    )


async def get_cursor(session: AsyncSession, project_id: int, stream: str) -> SyncCursor | None:
    return await session.scalar(
        select(SyncCursor).where(SyncCursor.project_id == project_id, SyncCursor.stream == stream)
    )


async def advance_cursor(
    session: AsyncSession,
    project_id: int,
    stream: str,
    synced_until: datetime,
    synced_from: datetime | None,
) -> None:
    stmt = insert(SyncCursor).values(
        project_id=project_id, stream=stream, synced_until=synced_until, synced_from=synced_from
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[SyncCursor.project_id, SyncCursor.stream],
            set_={"synced_until": stmt.excluded.synced_until},
        )
    )


def _excluded(stmt: Any, *columns: str) -> dict[str, Any]:
    return {column: getattr(stmt.excluded, column) for column in columns}
