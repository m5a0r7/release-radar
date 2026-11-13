import re
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from typing import Any

from radar.connectors.base import (
    EventField,
    EventRecord,
    ReleaseRecord,
    StatusCategory,
    TrackerProjectRecord,
    WorkItemRecord,
)
from radar.connectors.http import RetryingFetcher

PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
VERSION_ID_RE = re.compile(r"^\d{1,20}$")

SEARCH_FIELDS = (
    "summary,issuetype,status,priority,assignee,fixVersions,created,updated,resolutiondate"
)

# Jira changelog field name -> normalized event field. Release events carry version ids.
TRACKED_FIELDS = {
    "Fix Version": EventField.RELEASE,
    "status": EventField.STATUS,
    "resolution": EventField.RESOLUTION,
    "assignee": EventField.ASSIGNEE,
}
ID_VALUED_FIELDS = frozenset({EventField.RELEASE})

STATUS_CATEGORIES = {
    "new": StatusCategory.TODO,
    "indeterminate": StatusCategory.IN_PROGRESS,
    "done": StatusCategory.DONE,
}


class JiraTracker:
    """Jira Server / Data Center REST v2, used anonymously against public instances."""

    name = "jira"

    def __init__(self, fetcher: RetryingFetcher, page_size: int, base_url: str) -> None:
        self._fetcher = fetcher
        self._page_size = page_size
        self._base = base_url.rstrip("/")

    def item_url_template(self, project_key: str) -> str:
        return f"{self._base}/browse/{{key}}"

    def search_url_template(self, project_key: str) -> str:
        return f"{self._base}/issues/?jql=key%20in%20({{keys}})"

    async def describe_project(self, project_key: str) -> TrackerProjectRecord:
        _require(PROJECT_KEY_RE, project_key, "project key")
        raw = (await self._fetcher.get(f"rest/api/2/project/{project_key}")).json()
        return TrackerProjectRecord(key=raw["key"], name=raw.get("name") or raw["key"])

    async def list_releases(self, project_key: str) -> list[ReleaseRecord]:
        _require(PROJECT_KEY_RE, project_key, "project key")
        response = await self._fetcher.get(f"rest/api/2/project/{project_key}/versions")
        return [_parse_release(raw) for raw in response.json()]

    async def iter_release_items(
        self, project_key: str, release_external_id: str, updated_since: datetime | None
    ) -> AsyncIterator[list[WorkItemRecord]]:
        _require(PROJECT_KEY_RE, project_key, "project key")
        _require(VERSION_ID_RE, release_external_id, "release id")
        # Inputs are validated against strict patterns above, so the JQL cannot be injected.
        # `WAS` also returns items later moved out of the release, which is what scope-churn needs.
        jql = f"project = {project_key} AND fixVersion WAS {release_external_id}"
        if updated_since is not None:
            # JQL dates are interpreted in the server's timezone; a one-day overlap keeps the
            # incremental window safe, and upserts make the overlap harmless.
            since = (updated_since - timedelta(days=1)).date().isoformat()
            jql += f' AND updated >= "{since}"'
        jql += " ORDER BY key ASC"

        start_at = 0
        while True:
            response = await self._fetcher.get(
                "rest/api/2/search",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": self._page_size,
                    "fields": SEARCH_FIELDS,
                    "expand": "changelog",
                },
            )
            body = response.json()
            issues: list[dict[str, Any]] = body.get("issues", [])
            if not issues:
                return
            yield [await self._parse_issue(issue) for issue in issues]
            start_at += len(issues)
            if start_at >= int(body.get("total", 0)):
                return

    async def _parse_issue(self, raw: dict[str, Any]) -> WorkItemRecord:
        changelog = raw.get("changelog") or {}
        histories = changelog.get("histories", [])
        if int(changelog.get("total", 0)) > len(histories):
            full = await self._fetcher.get(
                f"rest/api/2/issue/{raw['id']}", params={"expand": "changelog", "fields": "none"}
            )
            histories = full.json().get("changelog", {}).get("histories", [])

        fields = raw["fields"]
        status = fields["status"]
        resolved = fields.get("resolutiondate")
        return WorkItemRecord(
            external_id=str(raw["id"]),
            key=raw["key"],
            title=fields.get("summary") or "",
            item_type=(fields.get("issuetype") or {}).get("name", "Unknown"),
            status=status["name"],
            status_category=STATUS_CATEGORIES.get(
                status.get("statusCategory", {}).get("key", ""), StatusCategory.TODO
            ),
            priority=(fields.get("priority") or {}).get("name"),
            assignee=(fields.get("assignee") or {}).get("displayName"),
            release_ids=tuple(str(v["id"]) for v in fields.get("fixVersions") or []),
            created_at=parse_jira_datetime(fields["created"]),
            updated_at=parse_jira_datetime(fields["updated"]),
            resolved_at=parse_jira_datetime(resolved) if resolved else None,
            events=tuple(_parse_events(histories)),
        )


def parse_jira_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")


def _parse_release(raw: dict[str, Any]) -> ReleaseRecord:
    release_date = raw.get("releaseDate")
    return ReleaseRecord(
        external_id=str(raw["id"]),
        name=raw["name"],
        released=bool(raw.get("released", False)),
        archived=bool(raw.get("archived", False)),
        release_date=date.fromisoformat(release_date) if release_date else None,
    )


def _parse_events(histories: list[dict[str, Any]]) -> list[EventRecord]:
    events: list[EventRecord] = []
    for history in histories:
        occurred_at = parse_jira_datetime(history["created"])
        for index, item in enumerate(history.get("items", [])):
            field = TRACKED_FIELDS.get(item.get("field", ""))
            if field is None:
                continue
            by_id = field in ID_VALUED_FIELDS
            events.append(
                EventRecord(
                    external_id=f"{history['id']}:{index}",
                    occurred_at=occurred_at,
                    field=field,
                    from_value=item.get("from") if by_id else item.get("fromString"),
                    to_value=item.get("to") if by_id else item.get("toString"),
                )
            )
    return events


def _require(pattern: re.Pattern[str], value: str, label: str) -> None:
    if not pattern.fullmatch(value):
        raise ValueError(f"invalid {label}: {value!r}")
