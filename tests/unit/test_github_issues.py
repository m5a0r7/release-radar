from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from radar.connectors.base import EventField, StatusCategory
from radar.connectors.errors import UpstreamNotFoundError
from radar.connectors.github_issues import GitHubIssuesTracker
from radar.connectors.http import RetryingFetcher

API = "https://api.github.test/"
REPO = "acme/widgets"
MILESTONES = [
    {"number": 2, "title": "v2.0", "state": "open", "due_on": "2026-12-01T08:00:00Z"},
    {"number": 1, "title": "v1.0", "state": "closed", "due_on": None},
]


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def tracker() -> AsyncIterator[GitHubIssuesTracker]:
    async with httpx.AsyncClient(base_url=API) as client:
        fetcher = RetryingFetcher(client, "github", 0, sleep=no_sleep, jitter=lambda: 0.0)
        yield GitHubIssuesTracker(fetcher, API)


def issue(number: int, **overrides: Any) -> dict[str, Any]:
    return {
        "id": 1000 + number,
        "number": number,
        "title": f"Issue {number}",
        "state": "open",
        "labels": [],
        "assignee": None,
        "milestone": {"number": 2, "title": "v2.0"},
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-11-01T00:00:00Z",
        "closed_at": None,
        **overrides,
    }


def event(event_id: int, kind: str, **fields: Any) -> dict[str, Any]:
    return {"id": event_id, "event": kind, "created_at": "2026-10-05T00:00:00Z", **fields}


@respx.mock
async def test_milestones_are_releases_oldest_first(tracker: GitHubIssuesTracker) -> None:
    respx.get(f"{API}repos/{REPO}/milestones").respond(200, json=MILESTONES)

    releases = await tracker.list_releases(REPO)

    assert [(r.external_id, r.name, r.released) for r in releases] == [
        ("1", "v1.0", True),
        ("2", "v2.0", False),
    ]
    assert releases[1].release_date is not None and releases[1].release_date.isoformat() == (
        "2026-12-01"
    )


@respx.mock
async def test_repository_without_issues_is_rejected(tracker: GitHubIssuesTracker) -> None:
    respx.get(f"{API}repos/{REPO}").respond(200, json={"full_name": REPO, "has_issues": False})

    with pytest.raises(UpstreamNotFoundError):
        await tracker.describe_project(REPO)


@respx.mock
async def test_issues_and_their_history_are_normalized(tracker: GitHubIssuesTracker) -> None:
    respx.get(f"{API}repos/{REPO}/milestones").respond(200, json=MILESTONES)
    respx.get(f"{API}repos/{REPO}/issues").respond(
        200,
        json=[
            issue(
                7,
                state="closed",
                closed_at="2026-10-20T00:00:00Z",
                labels=[{"name": "Bug"}],
                assignee={"login": "ada"},
            ),
            issue(8, assignee={"login": "lin"}),
            {**issue(9), "pull_request": {"url": "x"}},
        ],
    )
    respx.get(f"{API}repos/{REPO}/issues/7/events").respond(
        200,
        json=[
            event(1, "milestoned", milestone={"title": "v2.0"}),
            event(2, "assigned", assignee={"login": "ada"}),
            event(3, "closed", state_reason="completed"),
            event(4, "labeled", label={"name": "bug"}),
        ],
    )
    respx.get(f"{API}repos/{REPO}/issues/8/events").respond(
        200, json=[event(5, "milestoned", milestone={"title": "renamed"})]
    )
    respx.get(f"{API}repos/{REPO}/issues/events").respond(
        200,
        json=[
            event(
                6,
                "demilestoned",
                milestone={"title": "v2.0"},
                issue=issue(10, milestone=None),
            ),
            event(7, "demilestoned", milestone={"title": "v1.0"}, issue=issue(11)),
        ],
    )
    respx.get(f"{API}repos/{REPO}/issues/10/events").respond(
        200,
        json=[
            event(8, "milestoned", milestone={"title": "v2.0"}),
            event(9, "demilestoned", milestone={"title": "v2.0"}),
        ],
    )

    pages = [page async for page in tracker.iter_release_items(REPO, "2", None)]
    items = {item.key: item for page in pages for item in page}

    assert set(items) == {"#7", "#8", "#10"}
    done, active, removed = items["#7"], items["#8"], items["#10"]
    assert done.item_type == "Bug" and done.status_category is StatusCategory.DONE
    assert done.resolved_at == datetime(2026, 10, 20, tzinfo=UTC)
    assert [(e.field, e.from_value, e.to_value) for e in done.events] == [
        (EventField.RELEASE, None, "2"),
        (EventField.ASSIGNEE, None, "ada"),
        (EventField.RESOLUTION, None, "completed"),
    ]
    assert active.status_category is StatusCategory.IN_PROGRESS
    assert active.events[0].to_value == "title:renamed"
    assert removed.release_ids == ()
    assert [(e.from_value, e.to_value) for e in removed.events] == [(None, "2"), ("2", None)]


def test_item_urls_point_at_the_web_ui() -> None:
    fetcher = RetryingFetcher(httpx.AsyncClient(), "github", 0)
    tracker = GitHubIssuesTracker(fetcher, "https://api.github.com")

    assert tracker.item_url_template(REPO) == "https://github.com/acme/widgets/issues/{number}"
    assert tracker.search_url_template(REPO) == ""
