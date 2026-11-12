"""A small upstream world shared by the API tests: one Jira project, three tickets, three PRs."""

from typing import Any

import httpx

from radar.jobs.worker import Worker
from tests.factories import github_pull, jira_history, jira_issue

PROJECT = {"slug": "demo", "tracker_key": "DEMO", "repository": "apache/demo"}
VERSIONS = [
    {"id": "99", "name": "0.9", "released": True, "releaseDate": "2026-01-15"},
    {"id": "100", "name": "1.0", "released": False},
]
PERIOD = "from=2026-03-02&to=2026-03-29"
DRIFT = f"/v1/projects/demo/releases/1.0/drift?{PERIOD}"


def issues() -> list[dict[str, Any]]:
    resolution = {"field": "resolution", "fromString": None, "toString": "Fixed"}
    return [
        jira_issue(
            "DEMO-1",
            "1",
            fix_versions=["100"],
            category="done",
            created="2026-02-01T09:00:00.000+0000",
            resolved="2026-03-10T12:00:00.000+0000",
            histories=[jira_history("h1", "2026-03-10T12:00:00.000+0000", resolution)],
        ),
        jira_issue(
            "DEMO-2",
            "2",
            fix_versions=["100"],
            category="done",
            created="2026-02-01T09:00:00.000+0000",
            resolved="2026-03-15T12:00:00.000+0000",
            histories=[
                jira_history(
                    "h2",
                    "2026-03-15T12:00:00.000+0000",
                    {"field": "Fix Version", "from": None, "to": "100"},
                    resolution,
                )
            ],
        ),
        jira_issue("DEMO-3", "3", fix_versions=["100"], created="2026-02-01T09:00:00.000+0000"),
    ]


def pulls() -> list[dict[str, Any]]:
    return [
        github_pull(
            3, "DEMO-3: wip", updated="2026-03-20T00:00:00Z", merged="2026-03-20T00:00:00Z"
        ),
        github_pull(
            2, "MINOR: cleanup", updated="2026-03-12T00:00:00Z", merged="2026-03-12T00:00:00Z"
        ),
        github_pull(
            1, "DEMO-1: fix", updated="2026-03-10T00:00:00Z", merged="2026-03-10T00:00:00Z"
        ),
    ]


async def synced(client: httpx.AsyncClient, worker: Worker) -> dict[str, Any]:
    assert (await client.post("/v1/projects", json=PROJECT)).status_code == 201
    started = await client.post("/v1/projects/demo/releases/1.0/syncs")
    assert started.status_code == 202
    assert await worker.run_once()
    job: dict[str, Any] = (await client.get(started.headers["location"])).json()
    return job
