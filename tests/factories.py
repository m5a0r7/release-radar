"""Builders for history objects and upstream payloads used across tests."""

from datetime import UTC, date, datetime
from typing import Any

from radar.connectors.base import EventField
from radar.insights.drift import ChangeHistory, DriftInputs
from radar.insights.schemas import Coverage, ReleaseSummary
from radar.insights.timeline import Event, ItemHistory

RELEASE = "100"


def at(day: str, hour: int = 12) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=UTC)


def added(day: str, release: str = RELEASE, hour: int = 12) -> Event:
    return Event(at(day, hour), EventField.RELEASE, None, release)


def removed(day: str, release: str = RELEASE) -> Event:
    return Event(at(day), EventField.RELEASE, release, None)


def resolved(day: str, hour: int = 12) -> Event:
    return Event(at(day, hour), EventField.RESOLUTION, None, "Fixed")


def reopened(day: str) -> Event:
    return Event(at(day), EventField.RESOLUTION, "Fixed", None)


def item(
    key: str,
    created: str,
    *events: Event,
    resolved_at: datetime | None = None,
    in_release: bool = True,
) -> ItemHistory:
    resolution_events = [e for e in events if e.field == EventField.RESOLUTION]
    if resolved_at is None and resolution_events and resolution_events[-1].to_value:
        resolved_at = resolution_events[-1].occurred_at
    return ItemHistory(
        key=key,
        created_at=at(created, 9),
        resolved_at=resolved_at,
        release_ids=frozenset({RELEASE}) if in_release else frozenset(),
        events=tuple(events),
    )


def jira_issue(
    key: str,
    issue_id: str,
    *,
    fix_versions: list[str],
    created: str = "2026-01-05T10:00:00.000+0000",
    resolved: str | None = None,
    status: str = "Open",
    category: str = "new",
    histories: list[dict[str, Any]] | None = None,
    changelog_total: int | None = None,
) -> dict[str, Any]:
    histories = histories or []
    return {
        "id": issue_id,
        "key": key,
        "fields": {
            "summary": f"Summary of {key}",
            "issuetype": {"name": "Bug"},
            "status": {"name": status, "statusCategory": {"key": category}},
            "priority": {"name": "Major"},
            "assignee": {"displayName": "Ada"},
            "fixVersions": [{"id": v, "name": f"v{v}"} for v in fix_versions],
            "created": created,
            "updated": resolved or created,
            "resolutiondate": resolved,
        },
        "changelog": {
            "total": changelog_total if changelog_total is not None else len(histories),
            "histories": histories,
        },
    }


def jira_history(history_id: str, created: str, *items: dict[str, Any]) -> dict[str, Any]:
    return {"id": history_id, "created": created, "items": list(items)}


def github_pull(
    number: int,
    title: str,
    *,
    updated: str,
    merged: str | None = None,
    state: str = "closed",
) -> dict[str, Any]:
    return {
        "id": 10_000 + number,
        "number": number,
        "title": title,
        "user": {"login": "dev"},
        "state": state,
        "html_url": f"https://github.com/apache/demo/pull/{number}",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": updated,
        "merged_at": merged,
        "closed_at": merged,
    }


COVERAGE = Coverage(
    work_items_synced_at=None,
    code_changes_synced_from=None,
    code_changes_synced_at=None,
    complete=True,
    notes=[],
)


def drift_inputs(
    items: list[ItemHistory],
    *,
    start: date = date(2026, 3, 2),
    end: date = date(2026, 3, 29),
    changes: list[ChangeHistory] | None = None,
    merged: int = 0,
    unlinked: int = 0,
    target: date | None = None,
) -> DriftInputs:
    return DriftInputs(
        project="demo",
        release=ReleaseSummary(
            id=1, name="1.0", released=False, release_date=None, target_date=target
        ),
        release_external_id=RELEASE,
        items=items,
        linked_changes=changes or [],
        code_available=True,
        project_merged_in_period=merged,
        project_unlinked_merged_in_period=unlinked,
        coverage=COVERAGE,
        start=start,
        end=end,
    )


def scenario() -> DriftInputs:
    status_change = Event(at("2026-03-25"), EventField.STATUS, "Open", "In Progress")
    return drift_inputs(
        [
            item("K-A", "2026-02-01", resolved("2026-03-10")),
            item("K-B", "2026-02-01", added("2026-03-15", hour=10), resolved("2026-03-15")),
            item("K-C", "2026-02-01"),
            item("K-D", "2026-02-01", status_change),
            item("K-E", "2026-02-01", removed("2026-03-05"), in_release=False),
            item("K-F", "2026-02-01", resolved("2026-02-20")),
            item("K-G", "2026-02-01"),
        ],
        changes=[
            ChangeHistory(1, ("K-G",), at("2026-03-20"), at("2026-03-20")),
            ChangeHistory(2, ("K-A",), at("2026-03-10"), at("2026-03-10")),
            ChangeHistory(3, ("K-A",), None, at("2026-04-15")),
        ],
        merged=5,
        unlinked=2,
    )
