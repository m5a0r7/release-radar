from datetime import timedelta
from typing import Any

import httpx
import respx
from sqlalchemy import func, select, update

from radar.container import Container
from radar.db.models import Job
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
