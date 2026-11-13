import asyncio
import contextlib
import signal
import time
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radar.config import Settings, get_settings
from radar.connectors.errors import RateLimitedError, UpstreamNotFoundError
from radar.connectors.registry import Connectors
from radar.db.models import Job, Project, Release
from radar.db.session import create_engine, create_session_factory, transaction
from radar.ingest.service import SyncService, SyncTooLargeError
from radar.jobs import queue
from radar.jobs.scheduler import schedule_due_syncs
from radar.logging import configure_logging

log = structlog.get_logger(__name__)

SCHEDULE_CHECK_SECONDS = 60.0


class Worker:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        sync_service: SyncService,
        settings: Settings,
    ) -> None:
        self._sessions = sessions
        self._sync = sync_service
        self._settings = settings
        self._next_schedule_check = 0.0

    async def run(self, stop: asyncio.Event) -> None:
        log.info("worker_started")
        while not stop.is_set():
            await self.schedule_if_due()
            if await self.run_once():
                continue
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self._settings.worker_poll_interval_seconds)
        log.info("worker_stopped")

    async def schedule_if_due(self) -> None:
        if self._settings.auto_sync_hours <= 0 or time.monotonic() < self._next_schedule_check:
            return
        self._next_schedule_check = time.monotonic() + SCHEDULE_CHECK_SECONDS
        try:
            async with transaction(self._sessions) as session:
                queued = await schedule_due_syncs(
                    session,
                    timedelta(hours=self._settings.auto_sync_hours),
                    self._settings.job_max_attempts,
                )
        except Exception:
            log.exception("schedule_failed")
            return
        if queued:
            log.info("scheduled_syncs", count=queued)

    async def run_once(self) -> bool:
        """Claim and execute one job. Returns False when the queue had nothing due."""
        async with transaction(self._sessions) as session:
            job = await queue.claim(session, self._settings.job_lease_seconds)
        if job is None:
            return False

        structlog.contextvars.bind_contextvars(job_id=job.id, job_kind=job.kind)
        try:
            await self._execute(job)
        finally:
            structlog.contextvars.unbind_contextvars("job_id", "job_kind")
        return True

    async def _execute(self, job: Job) -> None:
        if job.attempts > job.max_attempts:
            await self._fail(job, "lease expired too many times", retryable=False)
            return
        try:
            progress = await self._dispatch(job)
        except queue.JobCancelled:
            log.info("job_cancelled")
        except RateLimitedError as exc:
            log.warning("job_rate_limited", retry_at=exc.retry_at.isoformat())
            await self._fail(job, str(exc), retry_at=exc.retry_at, count_attempt=False)
        except (UpstreamNotFoundError, SyncTooLargeError) as exc:
            log.warning("job_failed_permanently", error=str(exc))
            await self._fail(job, str(exc), retryable=False)
        except Exception as exc:
            log.exception("job_failed")
            await self._fail(job, f"{type(exc).__name__}: {exc}")
        else:
            async with transaction(self._sessions) as session:
                await queue.succeed(session, job.id, progress)
            log.info("job_succeeded")

    async def _dispatch(self, job: Job) -> dict[str, Any]:
        if job.kind != queue.SYNC_RELEASE:
            raise ValueError(f"unknown job kind: {job.kind}")
        async with self._sessions() as session:
            project = await session.get(Project, job.project_id)
            release = await session.get(Release, int(job.payload["release_id"]))
        if project is None or release is None:
            raise ValueError("project or release no longer exists")

        async def on_progress(progress: dict[str, Any]) -> None:
            async with transaction(self._sessions) as session:
                if not await queue.heartbeat(
                    session, job.id, self._settings.job_lease_seconds, progress
                ):
                    raise queue.JobCancelled

        result = await self._sync.sync_release(project, release, on_progress)
        return {"stage": "done", "work_items": result.items, "code_changes": result.changes}

    async def _fail(self, job: Job, error: str, **kwargs: Any) -> None:
        async with transaction(self._sessions) as session:
            await queue.fail(session, job, error[:2000], **kwargs)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    connectors = Connectors(settings)
    worker = Worker(
        sessions,
        SyncService(
            sessions, connectors, settings.github_backfill_days, settings.sync_max_work_items
        ),
        settings,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await worker.run(stop)
    finally:
        await connectors.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
