from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from radar.container import Container
from radar.db.models import Job
from radar.db.session import transaction
from radar.jobs import queue


async def enqueue(container: Container, key: str = "k") -> Job:
    async with transaction(container.sessions) as session:
        return await queue.enqueue(
            session, kind="noop", project_id=None, payload={}, dedupe_key=key, max_attempts=2
        )


async def claim(container: Container) -> Job | None:
    async with transaction(container.sessions) as session:
        return await queue.claim(session, lease_seconds=60)


async def test_claim_is_exclusive(container: Container) -> None:
    job = await enqueue(container)

    claimed = await claim(container)

    assert claimed is not None and claimed.id == job.id
    assert claimed.status == queue.RUNNING and claimed.attempts == 1
    assert await claim(container) is None


async def test_duplicate_active_job_is_rejected_but_finished_one_is_not(
    container: Container,
) -> None:
    job = await enqueue(container)
    with pytest.raises(queue.JobAlreadyActiveError):
        await enqueue(container)
    assert await claim(container) is not None

    async with transaction(container.sessions) as session:
        await queue.succeed(session, job.id, {})

    assert (await enqueue(container)).id != job.id


async def test_expired_lease_is_reclaimed(container: Container) -> None:
    job = await enqueue(container)
    await claim(container)
    async with transaction(container.sessions) as session:
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    reclaimed = await claim(container)

    assert reclaimed is not None and reclaimed.attempts == 2


async def test_failures_retry_then_fail_permanently(container: Container) -> None:
    await enqueue(container)
    for expected in (queue.QUEUED, queue.FAILED):
        job = await claim(container)
        assert job is not None
        async with transaction(container.sessions) as session:
            await queue.fail(session, job, "boom", retry_at=datetime.now(UTC))
            refreshed = await session.get(Job, job.id)
            assert refreshed is not None and refreshed.status == expected


async def test_cancel_stops_the_job_and_allows_another(container: Container) -> None:
    job = await enqueue(container)
    async with transaction(container.sessions) as session:
        assert await queue.cancel(session, job.id)
        stopped = await session.get(Job, job.id)
    assert stopped is not None and stopped.status == queue.CANCELLED
    assert await claim(container) is None

    again = await enqueue(container)
    assert again.id != job.id


async def test_a_stopped_job_is_not_requeued(container: Container) -> None:
    job = await enqueue(container)
    running = await claim(container)
    assert running is not None
    async with transaction(container.sessions) as session:
        await queue.cancel(session, job.id)
        await queue.fail(session, running, "github: rate limited until later", count_attempt=False)
        stopped = await session.get(Job, job.id)
    assert stopped is not None and stopped.status == queue.CANCELLED


async def test_rate_limited_retry_does_not_consume_an_attempt(container: Container) -> None:
    await enqueue(container)
    job = await claim(container)
    assert job is not None
    retry_at = datetime.now(UTC) + timedelta(hours=1)

    async with transaction(container.sessions) as session:
        await queue.fail(session, job, "limited", retry_at=retry_at, count_attempt=False)
        refreshed = await session.get(Job, job.id)

    assert refreshed is not None
    assert (refreshed.status, refreshed.attempts) == (queue.QUEUED, 0)
    assert await claim(container) is None
