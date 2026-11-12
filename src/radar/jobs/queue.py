"""A small durable job queue on Postgres.

Workers claim rows with `FOR UPDATE SKIP LOCKED`, so several can run concurrently. A claim is a
lease: a worker that dies stops renewing it and the job becomes claimable again. A partial unique
index on `dedupe_key` guarantees at most one active job per key (e.g. one sync per release).
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import Job

SYNC_RELEASE = "sync_release"

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"


class JobAlreadyActiveError(Exception):
    def __init__(self, job: Job) -> None:
        super().__init__(f"job {job.id} is already {job.status}")
        self.job = job


async def enqueue(
    session: AsyncSession,
    *,
    kind: str,
    project_id: int | None,
    payload: dict[str, Any],
    dedupe_key: str,
    max_attempts: int,
) -> Job:
    stmt = (
        insert(Job)
        .values(
            kind=kind,
            project_id=project_id,
            payload=payload,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(
            index_elements=[Job.dedupe_key],
            index_where=text("status IN ('queued', 'running')"),
        )
        .returning(Job)
    )
    job = await session.scalar(stmt)
    if job is not None:
        return job
    active = await session.scalar(
        select(Job).where(Job.dedupe_key == dedupe_key, Job.status.in_([QUEUED, RUNNING]))
    )
    if active is None:
        raise RuntimeError("enqueue conflicted but no active job was found")
    raise JobAlreadyActiveError(active)


async def claim(session: AsyncSession, lease_seconds: int) -> Job | None:
    """Atomically take the next due job, or one whose previous lease expired."""
    now = func.now()
    candidate = (
        select(Job.id)
        .where(
            ((Job.status == QUEUED) & (Job.run_after <= now))
            | ((Job.status == RUNNING) & (Job.lease_expires_at < now))
        )
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    return await session.scalar(
        update(Job)
        .where(Job.id == candidate)
        .values(
            status=RUNNING,
            attempts=Job.attempts + 1,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            started_at=func.coalesce(Job.started_at, now),
        )
        .returning(Job)
        .execution_options(synchronize_session=False)
    )


async def heartbeat(
    session: AsyncSession, job_id: int, lease_seconds: int, progress: dict[str, Any]
) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == RUNNING)
        .values(progress=progress, lease_expires_at=func.now() + timedelta(seconds=lease_seconds))
    )


async def succeed(session: AsyncSession, job_id: int, progress: dict[str, Any]) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status=SUCCEEDED,
            progress=progress,
            finished_at=func.now(),
            lease_expires_at=None,
            last_error=None,
        )
    )


async def fail(
    session: AsyncSession,
    job: Job,
    error: str,
    *,
    retry_at: datetime | None = None,
    count_attempt: bool = True,
    retryable: bool = True,
) -> None:
    """Reschedule the job if it is retryable and has attempts left, otherwise mark it failed."""
    attempts = job.attempts if count_attempt else job.attempts - 1
    if retryable and attempts < job.max_attempts:
        backoff = timedelta(seconds=30 * 2 ** max(attempts - 1, 0))
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                status=QUEUED,
                attempts=attempts,
                run_after=retry_at or datetime.now(UTC) + backoff,
                lease_expires_at=None,
                last_error=error,
            )
        )
        return
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(status=FAILED, finished_at=func.now(), lease_expires_at=None, last_error=error)
    )
