"""GitHub Issues as a work tracker: milestones are releases, issues are work items.

Issue events (milestoned, demilestoned, closed, reopened, assigned) are mapped onto the same
normalized history as Jira's changelog, so the drift metrics need no GitHub-specific code.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from radar.connectors.base import (
    EventField,
    EventRecord,
    ReleaseRecord,
    StatusCategory,
    TrackerProjectRecord,
    WorkItemRecord,
)
from radar.connectors.errors import UpstreamNotFoundError
from radar.connectors.github import next_page, parse_time, require_repository
from radar.connectors.http import RetryingFetcher

PAGE_SIZE = 100
# Issues are saved in small groups so a sync reports progress before a whole page is done.
ITEM_BATCH = 8
# Bounds per-issue history requests; issues with more events than this are rare.
MAX_EVENT_PAGES_PER_ISSUE = 5
# The repository-wide event feed is only scanned to find issues removed from a milestone.
MAX_REPOSITORY_EVENT_PAGES = 30
BUG_LABELS = frozenset({"bug", "type: bug", "kind/bug", "type/bug"})


class GitHubIssuesTracker:
    name = "github"

    def __init__(self, fetcher: RetryingFetcher, api_url: str) -> None:
        self._fetcher = fetcher
        self._api_host = httpx.URL(api_url).host
        self._web = _web_url(api_url)

    def item_url_template(self, project_key: str) -> str:
        return f"{self._web}/{project_key}/issues/{{number}}"

    def search_url_template(self, project_key: str) -> str:
        # GitHub search cannot list issues by number, so there is no multi-item view.
        return ""

    async def describe_project(self, project_key: str) -> TrackerProjectRecord:
        require_repository(project_key)
        raw = (await self._fetcher.get(f"repos/{project_key}")).json()
        if not raw.get("has_issues", True):
            raise UpstreamNotFoundError(self.name, f"{project_key} has GitHub Issues turned off")
        return TrackerProjectRecord(key=raw["full_name"], name=raw["full_name"])

    async def list_releases(self, project_key: str) -> list[ReleaseRecord]:
        require_repository(project_key)
        milestones = await self._milestones(project_key)
        # Oldest first, like Jira's version list.
        return [_parse_milestone(m) for m in sorted(milestones, key=lambda m: m["number"])]

    async def iter_release_items(
        self, project_key: str, release_external_id: str, updated_since: datetime | None
    ) -> AsyncIterator[list[WorkItemRecord]]:
        require_repository(project_key)
        if not release_external_id.isdigit():
            raise ValueError(f"invalid milestone number: {release_external_id!r}")
        milestones = {m["title"]: str(m["number"]) for m in await self._milestones(project_key)}
        title = next((t for t, n in milestones.items() if n == release_external_id), None)
        # The overlap keeps the incremental window safe; upserts make re-reads harmless.
        since = updated_since - timedelta(days=1) if updated_since else None

        seen: set[int] = set()
        params: dict[str, str | int] = {
            "milestone": release_external_id,
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": PAGE_SIZE,
        }
        if since is not None:
            params["since"] = since.isoformat()
        async for page in self._pages(f"repos/{project_key}/issues", params):
            issues = [raw for raw in page if "pull_request" not in raw]
            seen.update(raw["number"] for raw in issues)
            for start in range(0, len(issues), ITEM_BATCH):
                chunk = issues[start : start + ITEM_BATCH]
                yield list(
                    await asyncio.gather(
                        *(self._item(project_key, raw, milestones) for raw in chunk)
                    )
                )

        # Issues moved out of the milestone are no longer listed under it; find them through
        # the repository's recent `demilestoned` events so scope removals are counted.
        if title is None:
            return
        removed = await self._removed_issues(project_key, title, since, seen)
        if removed:
            yield [await self._item(project_key, raw, milestones) for raw in removed]

    async def _milestones(self, repository: str) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"state": "all", "per_page": PAGE_SIZE}
        return [
            m async for page in self._pages(f"repos/{repository}/milestones", params) for m in page
        ]

    async def _removed_issues(
        self, repository: str, title: str, since: datetime | None, seen: set[int]
    ) -> list[dict[str, Any]]:
        found: dict[int, dict[str, Any]] = {}
        pages = 0
        params: dict[str, str | int] = {"per_page": PAGE_SIZE}
        async for page in self._pages(f"repos/{repository}/issues/events", params):
            pages += 1
            for event in page:
                created = parse_time(event.get("created_at"))
                if since is not None and created is not None and created < since:
                    return list(found.values())
                issue = event.get("issue") or {}
                if (
                    event.get("event") == "demilestoned"
                    and (event.get("milestone") or {}).get("title") == title
                    and "pull_request" not in issue
                    and issue.get("number") not in seen
                ):
                    found[issue["number"]] = issue
            if pages >= MAX_REPOSITORY_EVENT_PAGES:
                break
        return list(found.values())

    async def _item(
        self, repository: str, raw: dict[str, Any], milestones: dict[str, str]
    ) -> WorkItemRecord:
        events = await self._events(repository, raw["number"], milestones)
        closed = raw.get("state") == "closed"
        labels = {(label.get("name") or "").lower() for label in raw.get("labels") or []}
        milestone = raw.get("milestone")
        assignee = (raw.get("assignee") or {}).get("login")
        return WorkItemRecord(
            external_id=str(raw["id"]),
            key=f"#{raw['number']}",
            title=raw.get("title") or "",
            item_type="Bug" if labels & BUG_LABELS else "Issue",
            status="closed" if closed else "open",
            status_category=StatusCategory.DONE
            if closed
            else StatusCategory.IN_PROGRESS
            if assignee
            else StatusCategory.TODO,
            priority=None,
            assignee=assignee,
            release_ids=(str(milestone["number"]),) if milestone else (),
            created_at=datetime.fromisoformat(raw["created_at"]),
            updated_at=datetime.fromisoformat(raw["updated_at"]),
            resolved_at=parse_time(raw.get("closed_at")) if closed else None,
            events=tuple(events),
        )

    async def _events(
        self, repository: str, number: int, milestones: dict[str, str]
    ) -> list[EventRecord]:
        events: list[EventRecord] = []
        pages = 0
        params: dict[str, str | int] = {"per_page": PAGE_SIZE}
        async for page in self._pages(f"repos/{repository}/issues/{number}/events", params):
            events += [e for raw in page if (e := _parse_event(raw, milestones)) is not None]
            pages += 1
            if pages >= MAX_EVENT_PAGES_PER_ISSUE:
                break
        return events

    async def _pages(
        self, url: str, params: dict[str, str | int]
    ) -> AsyncIterator[list[dict[str, Any]]]:
        next_url: str | None = url
        query: dict[str, str | int] | None = params
        while next_url is not None:
            response = await self._fetcher.get(next_url, params=query)
            yield response.json()
            next_url = next_page(response, self._api_host)
            query = None


def _web_url(api_url: str) -> str:
    """https://api.github.com -> https://github.com; GitHub Enterprise drops `/api/v3`."""
    url = httpx.URL(api_url)
    if url.host == "api.github.com":
        return "https://github.com"
    return str(url.copy_with(path="")).rstrip("/")


def _parse_milestone(raw: dict[str, Any]) -> ReleaseRecord:
    due = raw.get("due_on")
    return ReleaseRecord(
        external_id=str(raw["number"]),
        name=raw["title"],
        released=raw.get("state") == "closed",
        archived=False,
        release_date=date.fromisoformat(due[:10]) if due else None,
    )


def _parse_event(raw: dict[str, Any], milestones: dict[str, str]) -> EventRecord | None:
    kind = raw.get("event")
    at = datetime.fromisoformat(raw["created_at"])
    event_id = str(raw["id"])

    def record(field: EventField, before: str | None, after: str | None) -> EventRecord:
        return EventRecord(event_id, at, field, before, after)

    if kind in ("milestoned", "demilestoned"):
        title = (raw.get("milestone") or {}).get("title", "")
        # Events carry the milestone title only; a renamed or deleted one keeps its old title.
        milestone = milestones.get(title, f"title:{title}")
        if kind == "milestoned":
            return record(EventField.RELEASE, None, milestone)
        return record(EventField.RELEASE, milestone, None)
    if kind == "closed":
        return record(EventField.RESOLUTION, None, raw.get("state_reason") or "completed")
    if kind == "reopened":
        return record(EventField.RESOLUTION, "completed", None)
    if kind in ("assigned", "unassigned"):
        login = (raw.get("assignee") or {}).get("login")
        if kind == "assigned":
            return record(EventField.ASSIGNEE, None, login)
        return record(EventField.ASSIGNEE, login, None)
    return None
