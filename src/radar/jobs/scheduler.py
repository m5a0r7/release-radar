"""Periodic re-syncs. Any worker may run this: the queue's dedupe index makes it safe to race."""

from datetime import timedelta

from sqlalchemy import BigInteger, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import Job, Release
from radar.jobs import queue


async def schedule_due_syncs(session: AsyncSession, every: timedelta, max_attempts: int) -> int:
    """Queue a sync for each tracked, upcoming release whose last sync finished `every` ago.

    Tracked means synced at least once. Failed syncs count as finished, so a release that keeps
    failing is retried once per interval instead of in a tight loop.
    """
    release_id = Job.payload["release_id"].astext.cast(BigInteger)
    history = (
        select(
            release_id.label("release_id"),
            Job.project_id,
            func.max(Job.finished_at).label("finished_at"),
            func.count().filter(Job.status.in_([queue.QUEUED, queue.RUNNING])).label("active"),
        )
        .where(Job.kind == queue.SYNC_RELEASE)
        .group_by(release_id, Job.project_id)
        .subquery()
    )
    due = await session.execute(
        select(history.c.project_id, history.c.release_id)
        .join(Release, Release.id == history.c.release_id)
        .where(
            Release.released.is_(False),
            Release.archived.is_(False),
            history.c.active == 0,
            history.c.finished_at < func.now() - every,
        )
    )
    queued = 0
    for project_id, due_release_id in due:
        try:
            await queue.enqueue(
                session,
                kind=queue.SYNC_RELEASE,
                project_id=project_id,
                payload={"release_id": due_release_id, "scheduled": True},
                dedupe_key=f"{queue.SYNC_RELEASE}:{due_release_id}",
                max_attempts=max_attempts,
            )
            queued += 1
        except queue.JobAlreadyActiveError:
            continue
    return queued
