"""Source-agnostic records and the interfaces every connector implements.

Adding a new source (Linear, Azure DevOps, GitLab, ...) means implementing one of these
protocols; ingestion, insights and the API do not change.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol


class EventField(StrEnum):
    RELEASE = "release"
    STATUS = "status"
    RESOLUTION = "resolution"
    ASSIGNEE = "assignee"


class StatusCategory(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ChangeState(StrEnum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class ReleaseRecord:
    external_id: str
    name: str
    released: bool
    archived: bool
    release_date: date | None


@dataclass(frozen=True, slots=True)
class EventRecord:
    external_id: str
    occurred_at: datetime
    field: EventField
    from_value: str | None
    to_value: str | None


@dataclass(frozen=True, slots=True)
class WorkItemRecord:
    external_id: str
    key: str
    title: str
    item_type: str
    status: str
    status_category: StatusCategory
    priority: str | None
    assignee: str | None
    release_ids: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    events: tuple[EventRecord, ...]


@dataclass(frozen=True, slots=True)
class CodeChangeRecord:
    external_id: str
    number: int
    title: str
    author: str | None
    state: ChangeState
    url: str
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class TrackerProjectRecord:
    key: str
    name: str


@dataclass(frozen=True, slots=True)
class RepositoryRecord:
    full_name: str
    description: str | None
    language: str | None
    stars: int
    pushed_at: datetime | None


class WorkTracker(Protocol):
    name: str
    item_url_template: str
    """Browser URL of an item, with `{key}` as the placeholder."""
    search_url_template: str
    """Browser URL listing items, with `{keys}` as a comma-separated placeholder."""

    async def describe_project(self, project_key: str) -> TrackerProjectRecord: ...

    async def list_releases(self, project_key: str) -> list[ReleaseRecord]: ...

    def iter_release_items(
        self, project_key: str, release_external_id: str, updated_since: datetime | None
    ) -> AsyncIterator[list[WorkItemRecord]]:
        """Yield pages of items that are, or ever were, part of the release."""
        ...


class CodeHost(Protocol):
    name: str

    async def recent_changes(self, repository: str, limit: int) -> list[CodeChangeRecord]:
        """The most recently created changes, to check how a repository links to tickets."""
        ...

    async def search_repositories(self, query: str, limit: int) -> list[RepositoryRecord]: ...

    def iter_changes(
        self, repository: str, updated_since: datetime
    ) -> AsyncIterator[list[CodeChangeRecord]]:
        """Yield pages of changes updated at or after `updated_since`, newest first."""
        ...
