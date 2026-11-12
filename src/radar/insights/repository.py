from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.connectors.base import EventField
from radar.db.models import CodeChange, Project, Release, SyncCursor, WorkItem, WorkItemEvent
from radar.ingest.service import code_stream, release_stream
from radar.insights.drift import ChangeHistory, DriftInputs
from radar.insights.schemas import Coverage, ReleaseSummary
from radar.insights.timeline import Event, ItemHistory


async def load_drift_inputs(
    session: AsyncSession,
    project: Project,
    release: Release,
    start: date,
    end: date,
    target_date: date | None,
    stale_after: timedelta = timedelta(hours=1),
) -> DriftInputs:
    ext = release.external_id
    ever_in_release = select(WorkItemEvent.work_item_id).where(
        WorkItemEvent.field == EventField.RELEASE.value,
        or_(WorkItemEvent.from_value == ext, WorkItemEvent.to_value == ext),
    )
    rows = (
        await session.scalars(
            select(WorkItem).where(
                WorkItem.project_id == project.id,
                or_(WorkItem.release_ids.contains([ext]), WorkItem.id.in_(ever_in_release)),
            )
        )
    ).all()

    events: dict[int, list[Event]] = defaultdict(list)
    if rows:
        for event in await session.scalars(
            select(WorkItemEvent).where(WorkItemEvent.work_item_id.in_([r.id for r in rows]))
        ):
            events[event.work_item_id].append(
                Event(event.occurred_at, event.field, event.from_value, event.to_value)
            )
    items = [
        ItemHistory(
            key=r.key,
            title=r.title,
            created_at=r.created_at,
            resolved_at=r.resolved_at,
            release_ids=frozenset(r.release_ids),
            events=tuple(events[r.id]),
        )
        for r in rows
    ]

    keys = [r.key for r in rows]
    linked = (
        (
            await session.scalars(
                select(CodeChange).where(
                    CodeChange.project_id == project.id, CodeChange.linked_keys.overlap(keys)
                )
            )
        ).all()
        if keys
        else []
    )

    start_at = datetime.combine(start, time.min, tzinfo=UTC)
    end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    merged_total, merged_unlinked = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(func.cardinality(CodeChange.linked_keys) == 0),
            ).where(
                CodeChange.project_id == project.id,
                CodeChange.merged_at >= start_at,
                CodeChange.merged_at < end_at,
            )
        )
    ).one()

    return DriftInputs(
        project=project.slug,
        release=ReleaseSummary(
            id=release.id,
            name=release.name,
            released=release.released,
            release_date=release.release_date,
            target_date=target_date or release.target_date or release.release_date,
        ),
        release_external_id=ext,
        items=items,
        linked_changes=[
            ChangeHistory(c.number, tuple(c.linked_keys), c.merged_at, c.updated_at) for c in linked
        ],
        code_available=project.code_host is not None,
        project_merged_in_period=merged_total,
        project_unlinked_merged_in_period=merged_unlinked,
        coverage=await _coverage(session, project, release, start_at, end_at, stale_after),
        start=start,
        end=end,
    )


async def _coverage(
    session: AsyncSession,
    project: Project,
    release: Release,
    start_at: datetime,
    end_at: datetime,
    stale_after: timedelta,
) -> Coverage:
    streams = [release_stream(project.tracker, release.external_id)]
    if project.code_host:
        streams.append(code_stream(project.code_host))
    cursors = {
        c.stream: c
        for c in await session.scalars(
            select(SyncCursor).where(
                SyncCursor.project_id == project.id, SyncCursor.stream.in_(streams)
            )
        )
    }
    work = cursors.get(streams[0])
    code = cursors.get(streams[1]) if len(streams) > 1 else None
    # A period ending today can only be covered up to "now", less the expected sync lag.
    end_at = min(end_at, datetime.now(UTC)) - stale_after

    notes: list[str] = []
    if work is None:
        notes.append("Work items have not been synced yet.")
    elif work.synced_until < end_at:
        notes.append("Work items were last synced before the period end.")
    if project.code_host:
        if code is None:
            notes.append("Code changes have not been synced yet.")
        else:
            if code.synced_from is not None and code.synced_from > start_at:
                notes.append(
                    "Code changes are only synced from "
                    f"{code.synced_from.date().isoformat()}; earlier PRs are missing."
                )
            if code.synced_until < end_at:
                notes.append("Code changes were last synced before the period end.")
    return Coverage(
        work_items_synced_at=work.synced_until if work else None,
        code_changes_synced_from=code.synced_from if code else None,
        code_changes_synced_at=code.synced_until if code else None,
        complete=not notes,
        notes=notes,
    )
