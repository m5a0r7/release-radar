from datetime import timedelta
from typing import Any

import httpx
import respx
from sqlalchemy import func, select, update

from radar.config import Settings
from radar.container import Container
from radar.db.models import Job
from radar.ingest.service import SyncService
from radar.jobs.scheduler import schedule_due_syncs
from radar.jobs.worker import Worker
from tests.factories import github_pull
from tests.integration.conftest import GITHUB, JIRA
from tests.integration.demo import PERIOD, synced

VERSIONS = [
    {"id": "1", "name": "0.9", "released": True},
    {"id": "2", "name": "1.0", "released": False},
    {"id": "3", "name": "1.1", "released": False},
    {"id": "4", "name": "old", "released": False, "archived": True},
]


async def test_tracker_check_lists_upcoming_releases(client: httpx.AsyncClient) -> None:
    with respx.mock:
        respx.get(f"{JIRA}rest/api/2/project/DEMO").respond(
            200, json={"key": "DEMO", "name": "Demo Project"}
        )
        respx.get(f"{JIRA}rest/api/2/project/DEMO/versions").respond(200, json=VERSIONS)
        response = await client.post("/v1/connect/tracker", json={"tracker_key": "DEMO"})

    assert response.json() == {
        "key": "DEMO",
        "name": "Demo Project",
        "upcoming_releases": ["1.1", "1.0"],
        "already_connected_as": None,
    }


async def test_unknown_tracker_project_is_a_clear_error(client: httpx.AsyncClient) -> None:
    with respx.mock:
        respx.get(f"{JIRA}rest/api/2/project/NOPE").respond(404)
        response = await client.post("/v1/connect/tracker", json={"tracker_key": "NOPE"})

    assert response.status_code == 422


async def test_code_check_reports_how_many_changes_reference_tickets(
    client: httpx.AsyncClient,
) -> None:
    pulls = [
        github_pull(3, "DEMO-7: fix", updated="2026-03-03T00:00:00Z"),
        github_pull(2, "MINOR: docs", updated="2026-03-02T00:00:00Z"),
        github_pull(1, "[demo-9] typo", updated="2026-03-01T00:00:00Z"),
    ]
    with respx.mock:
        route = respx.get(f"{GITHUB}repos/apache/demo/pulls").respond(200, json=pulls)
        response = await client.post(
            "/v1/connect/code", json={"repository": "apache/demo", "tracker_key": "DEMO"}
        )

    body = response.json()
    assert route.calls.last.request.url.params["sort"] == "created"
    assert (body["sampled"], body["linked"], body["linked_share"]) == (3, 2, 0.6667)
    assert [s["linked"] for s in body["samples"]] == [True, False, True]


async def test_repository_search_scopes_owner_and_hides_private(
    client: httpx.AsyncClient,
) -> None:
    items = [
        {
            "full_name": "apache/demo",
            "description": "d",
            "language": "Java",
            "stargazers_count": 5,
            "pushed_at": "2026-03-01T00:00:00Z",
            "private": False,
        },
        {"full_name": "apache/secret", "private": True},
    ]
    with respx.mock:
        route = respx.get(f"{GITHUB}search/repositories").respond(200, json={"items": items})
        response = await client.get("/v1/connect/repositories", params={"q": "apache/demo"})

    assert route.calls.last.request.url.params["q"] == "demo in:name user:apache"
    assert [r["full_name"] for r in response.json()] == ["apache/demo"]


async def test_target_date_is_saved_and_drives_the_forecast(
    client: httpx.AsyncClient, worker: Worker, upstream: Any
) -> None:
    await synced(client, worker)

    patched = await client.patch(
        "/v1/projects/demo/releases/1.0", json={"target_date": "2026-04-30"}
    )
    report = (await client.get(f"/v1/projects/demo/releases/1.0/drift?{PERIOD}")).json()
    project = (await client.get("/v1/projects/demo")).json()

    assert patched.json()["target_date"] == "2026-04-30"
    assert report["release"]["target_date"] == "2026-04-30"
    assert report["forecast"]["target_date"] == "2026-04-30"
    assert [r["name"] for r in project["tracked_releases"]] == ["1.0"]
    assert project["tracked_releases"][0]["sync_status"] == "succeeded"
    assert project["tracked_releases"][0]["last_synced_at"] is not None


async def test_tracked_releases_are_resynced_on_schedule(
    client: httpx.AsyncClient,
    worker: Worker,
    upstream: Any,
    container: Container,
) -> None:
    await synced(client, worker)
    every = timedelta(hours=6)

    async with container.sessions() as session, session.begin():
        assert await schedule_due_syncs(session, every, max_attempts=3) == 0
        await session.execute(update(Job).values(finished_at=func.now() - timedelta(hours=7)))
        assert await schedule_due_syncs(session, every, max_attempts=3) == 1
        assert await schedule_due_syncs(session, every, max_attempts=3) == 0
        jobs = await session.scalar(select(func.count()).select_from(Job))

    assert jobs == 2


async def test_tracker_key_must_match_the_tracker(client: httpx.AsyncClient) -> None:
    jira_repo = await client.post("/v1/connect/tracker", json={"tracker_key": "apache/demo"})
    github_key = await client.post(
        "/v1/connect/tracker", json={"tracker": "github", "tracker_key": "DEMO"}
    )

    assert jira_repo.status_code == github_key.status_code == 422
    assert "owner/name" in github_key.text


def github_issue(number: int, **overrides: Any) -> dict[str, Any]:
    return {
        "id": 5_000 + number,
        "number": number,
        "title": f"Issue {number}",
        "state": "open",
        "labels": [],
        "assignee": None,
        "milestone": {"number": 3, "title": "v1.0"},
        "created_at": "2026-02-01T00:00:00Z",
        "updated_at": "2026-03-10T00:00:00Z",
        "closed_at": None,
        **overrides,
    }


def github_issues_upstream(mock: respx.MockRouter) -> None:
    repo = f"{GITHUB}repos/acme/widgets"
    mock.get(repo).respond(200, json={"full_name": "acme/widgets", "has_issues": True})
    mock.get(f"{repo}/milestones").respond(
        200, json=[{"number": 3, "title": "v1.0", "state": "open", "due_on": None}]
    )
    mock.get(f"{repo}/issues").respond(
        200,
        json=[
            github_issue(1, state="closed", closed_at="2026-03-10T12:00:00Z"),
            github_issue(2),
        ],
    )
    milestoned = {
        "id": 1,
        "event": "milestoned",
        "created_at": "2026-02-01T00:00:00Z",
        "milestone": {"title": "v1.0"},
    }
    closed = {"id": 2, "event": "closed", "created_at": "2026-03-10T12:00:00Z"}
    mock.get(f"{repo}/issues/1/events").respond(200, json=[milestoned, closed])
    mock.get(f"{repo}/issues/2/events").respond(200, json=[{**milestoned, "id": 3}])
    mock.get(f"{repo}/issues/events").respond(200, json=[])
    pull = github_pull(
        9, "Fix widget", updated="2026-03-10T00:00:00Z", merged="2026-03-10T00:00:00Z"
    )
    mock.get(f"{repo}/pulls").respond(200, json=[{**pull, "body": "Fixes #1"}])


async def test_github_issues_project_syncs_and_links_prs_by_body(
    client: httpx.AsyncClient, worker: Worker
) -> None:
    project = {
        "slug": "widgets",
        "tracker": "github",
        "tracker_key": "acme/widgets",
        "repository": "acme/widgets",
    }
    with respx.mock(assert_all_called=False) as mock:
        github_issues_upstream(mock)
        check = await client.post(
            "/v1/connect/tracker", json={"tracker": "github", "tracker_key": "acme/widgets"}
        )
        created = await client.post("/v1/projects", json=project)
        started = await client.post("/v1/projects/widgets/releases/v1.0/syncs")
        assert await worker.run_once()
        job = (await client.get(started.headers["location"])).json()
    report = (await client.get(f"/v1/projects/widgets/releases/v1.0/drift?{PERIOD}")).json()

    assert check.json()["upcoming_releases"] == ["v1.0"]
    assert created.status_code == 201
    assert (
        created.json()["item_url_template"]
        == "https://api.github.test/acme/widgets/issues/{number}"
    )
    assert created.json()["search_url_template"] == ""
    assert job["status"] == "succeeded", job
    assert (report["progress"]["completed_in_period"], report["progress"]["open_at_end"]) == (1, 1)
    assert report["code"]["linked_merged_in_period"] == 1


async def test_oversized_release_fails_without_retrying(
    container: Container, client: httpx.AsyncClient, settings: Settings, upstream: Any
) -> None:
    small = Worker(
        container.sessions,
        SyncService(container.sessions, container.connectors, 730, max_work_items=2),
        settings,
    )

    job = await synced(client, small)

    assert job["status"] == "failed"
    assert job["attempts"] == 1
    assert "more than 2 tickets" in job["last_error"]
