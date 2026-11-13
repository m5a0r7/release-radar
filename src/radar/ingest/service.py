from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radar.connectors.registry import Connectors
from radar.db.models import Project, Release
from radar.db.session import transaction
from radar.ingest import store

log = structlog.get_logger(__name__)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


def release_stream(tracker: str, release_external_id: str) -> str:
    return f"{tracker}:release:{release_external_id}"


def code_stream(code_host: str) -> str:
    return f"{code_host}:changes"


@dataclass(frozen=True, slots=True)
class SyncResult:
    items: int
    changes: int


class SyncTooLargeError(Exception):
    """The release exceeds `sync_max_work_items`; retrying cannot help."""


class SyncService:
    """Pulls a release's work items and the project's code changes into Postgres.

    Each upstream page is committed in its own transaction and cursors advance only after a
    stream completes, so an interrupted sync resumes safely and re-runs are idempotent.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        connectors: Connectors,
        github_backfill_days: int,
        max_work_items: int = 20_000,
    ) -> None:
        self._sessions = session_factory
        self._max_items = max_work_items
        self._connectors = connectors
        self._backfill = timedelta(days=github_backfill_days)

    async def refresh_releases(self, session: AsyncSession, project: Project) -> None:
        tracker = self._connectors.tracker(project.tracker)
        releases = await tracker.list_releases(project.tracker_key)
        await store.upsert_releases(session, project.id, releases)

    async def sync_release(
        self, project: Project, release: Release, on_progress: ProgressCallback
    ) -> SyncResult:
        async with transaction(self._sessions) as session:
            await self.refresh_releases(session, project)

        items = await self._sync_items(project, release, on_progress)
        changes = await self._sync_changes(project, on_progress, items)
        log.info(
            "sync_completed",
            project=project.slug,
            release=release.name,
            items=items,
            changes=changes,
        )
        return SyncResult(items=items, changes=changes)

    async def _sync_items(
        self, project: Project, release: Release, on_progress: ProgressCallback
    ) -> int:
        tracker = self._connectors.tracker(project.tracker)
        stream = release_stream(project.tracker, release.external_id)
        started_at = datetime.now(UTC)
        async with self._sessions() as session:
            cursor = await store.get_cursor(session, project.id, stream)

        count = 0
        await on_progress({"stage": "work_items", "work_items": 0})
        async for page in tracker.iter_release_items(
            project.tracker_key,
            release.external_id,
            cursor.synced_until if cursor else None,
        ):
            if count + len(page) > self._max_items:
                raise SyncTooLargeError(
                    f"{release.name} has more than {self._max_items} tickets; "
                    "raise SYNC_MAX_WORK_ITEMS to track it"
                )
            async with transaction(self._sessions) as session:
                await store.upsert_work_items(session, project.id, page)
            count += len(page)
            await on_progress({"stage": "work_items", "work_items": count})

        async with transaction(self._sessions) as session:
            await store.advance_cursor(session, project.id, stream, started_at, None)
        return count

    async def _sync_changes(
        self, project: Project, on_progress: ProgressCallback, items: int
    ) -> int:
        if project.code_host is None or project.repository is None:
            return 0
        code_host = self._connectors.code_host(project.code_host)
        stream = code_stream(project.code_host)
        started_at = datetime.now(UTC)
        async with self._sessions() as session:
            cursor = await store.get_cursor(session, project.id, stream)
        since = cursor.synced_until if cursor else started_at - self._backfill

        count = 0
        async for page in code_host.iter_changes(project.repository, since):
            async with transaction(self._sessions) as session:
                await store.upsert_code_changes(
                    session, project.id, project.tracker_key, page, project.tracker
                )
            count += len(page)
            await on_progress({"stage": "code_changes", "work_items": items, "code_changes": count})

        async with transaction(self._sessions) as session:
            await store.advance_cursor(
                session, project.id, stream, started_at, cursor.synced_from if cursor else since
            )
        return count
