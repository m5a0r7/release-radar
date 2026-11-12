from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import CodeChange, WorkItem, WorkItemEvent
from radar.jobs.worker import Worker
from tests.integration.conftest import JIRA
from tests.integration.demo import DRIFT, PERIOD, PROJECT, synced


async def test_create_project_fetches_releases(client: httpx.AsyncClient, upstream: Any) -> None:
    created = await client.post("/v1/projects", json=PROJECT)
    duplicate = await client.post("/v1/projects", json=PROJECT)
    releases = await client.get("/v1/projects/demo/releases")

    assert created.status_code == 201
    assert created.headers["location"] == "/v1/projects/demo"
    assert created.json()["item_url_template"] == f"{JIRA}browse/{{key}}"
    assert duplicate.status_code == 409
    assert duplicate.headers["content-type"] == "application/problem+json"
    assert [r["name"] for r in releases.json()] == ["1.0", "0.9"]


async def test_unknown_upstream_project_is_rejected_and_not_saved(
    client: httpx.AsyncClient,
) -> None:
    with respx.mock:
        respx.get(f"{JIRA}rest/api/2/project/NOPE/versions").respond(404)
        response = await client.post(
            "/v1/projects", json={"slug": "nope", "tracker_key": "NOPE", "repository": "a/b"}
        )

    assert response.status_code == 422
    assert (await client.get("/v1/projects/nope")).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"slug": "Bad Slug", "tracker_key": "DEMO"},
        {"slug": "demo", "tracker_key": "DEMO OR 1=1"},
        {"slug": "demo", "tracker_key": "DEMO", "repository": "https://evil.test/x"},
        {"slug": "demo", "tracker_key": "DEMO", "unexpected": True},
    ],
)
async def test_invalid_project_input_is_rejected(
    client: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    response = await client.post("/v1/projects", json=body)

    assert response.status_code == 422
    assert response.json()["title"] == "Invalid request"


async def test_sync_job_lifecycle(client: httpx.AsyncClient, worker: Worker, upstream: Any) -> None:
    assert (await client.post("/v1/projects", json=PROJECT)).status_code == 201
    first = await client.post("/v1/projects/demo/releases/1.0/syncs")
    second = await client.post("/v1/projects/demo/releases/1.0/syncs")

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.headers["location"] == first.headers["location"]

    assert await worker.run_once()
    assert not await worker.run_once()
    job = (await client.get(first.headers["location"])).json()
    assert job["status"] == "succeeded"
    assert job["progress"] == {"stage": "done", "work_items": 3, "code_changes": 3}


async def test_resync_is_idempotent(
    client: httpx.AsyncClient, worker: Worker, upstream: Any, session: AsyncSession
) -> None:
    await synced(client, worker)
    assert (await client.post("/v1/projects/demo/releases/1.0/syncs")).status_code == 202
    assert await worker.run_once()

    counts = [
        await session.scalar(select(func.count()).select_from(model))
        for model in (WorkItem, WorkItemEvent, CodeChange)
    ]
    assert counts == [3, 3, 3]


async def test_drift_report_matches_source_data(
    client: httpx.AsyncClient, worker: Worker, upstream: Any
) -> None:
    await synced(client, worker)

    report = (await client.get(DRIFT)).json()

    assert report["scope"] | {"added_keys": None, "removed_keys": None} == {
        "at_start": 2,
        "at_end": 3,
        "added": 1,
        "removed": 0,
        "change_pct": 50.0,
        "added_keys": None,
        "removed_keys": None,
    }
    assert report["progress"]["completed_in_period"] == 2
    assert report["progress"]["open_at_end"] == 1
    assert report["planning"]["sample_keys"] == ["DEMO-2"]
    assert report["idle"]["idle_items"] == 0
    assert report["code"]["linked_merged_in_period"] == 2
    assert report["code"]["unlinked_share"] == round(1 / 3, 4)
    assert report["code"]["sample_keys"] == ["DEMO-3"]
    assert report["coverage"]["complete"] is True


async def test_drift_supports_conditional_requests(
    client: httpx.AsyncClient, worker: Worker, upstream: Any
) -> None:
    await synced(client, worker)
    first = await client.get(DRIFT)

    second = await client.get(DRIFT, headers={"If-None-Match": first.headers["etag"]})

    assert second.status_code == 304
    assert second.content == b""


@pytest.mark.parametrize(
    ("query", "detail"),
    [
        ("from=2026-03-10&to=2026-03-01", "'from' must be on or before 'to'."),
        ("from=2020-01-01&to=2026-03-01", "The period cannot exceed 366 days."),
        ("to=2999-01-01", "'to' cannot be in the future."),
    ],
)
async def test_invalid_periods_are_rejected(
    client: httpx.AsyncClient, worker: Worker, upstream: Any, query: str, detail: str
) -> None:
    await synced(client, worker)

    response = await client.get(f"/v1/projects/demo/releases/1.0/drift?{query}")

    assert response.status_code == 422
    assert response.json()["detail"] == detail


async def test_unknown_resources_return_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/projects/missing/releases/1.0/drift")).status_code == 404
    assert (await client.get("/v1/jobs/12345")).status_code == 404


async def test_narrative_is_grounded_and_cached(
    client: httpx.AsyncClient, worker: Worker, upstream: Any
) -> None:
    await synced(client, worker)
    url = f"/v1/projects/demo/releases/1.0/narrative?{PERIOD}"

    first = (await client.get(url)).json()
    second = (await client.get(url)).json()

    assert first["meta"]["provider"] == "template"
    assert first["meta"]["cached"] is False
    assert second["meta"]["cached"] is True
    assert first["findings"]
    for finding in first["findings"]:
        assert finding["evidence"]
        assert finding["confidence"] <= first["meta"]["confidence_cap"]
    assert first["caveats"]
