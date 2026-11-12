from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import respx

from radar.connectors.base import ChangeState, EventField, StatusCategory
from radar.connectors.errors import RateLimitedError, UpstreamError, UpstreamNotFoundError
from radar.connectors.github import GitHubCodeHost
from radar.connectors.http import RetryingFetcher
from radar.connectors.jira import JiraTracker
from tests.factories import github_pull, jira_history, jira_issue

JIRA = "https://jira.test/jira/"
GITHUB = "https://api.github.test/"


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def jira_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=JIRA) as client:
        yield client


@pytest.fixture
async def github_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=GITHUB) as client:
        yield client


def fetcher(client: httpx.AsyncClient, retries: int = 3) -> RetryingFetcher:
    return RetryingFetcher(client, "test", retries, sleep=no_sleep, jitter=lambda: 0.0)


@respx.mock
async def test_fetcher_retries_transient_errors(jira_client: httpx.AsyncClient) -> None:
    route = respx.get(f"{JIRA}x").mock(
        side_effect=[httpx.ConnectError("down"), httpx.Response(503), httpx.Response(200, json={})]
    )

    response = await fetcher(jira_client).get("x")

    assert response.status_code == 200
    assert route.call_count == 3


@respx.mock
async def test_fetcher_gives_up_after_max_retries(jira_client: httpx.AsyncClient) -> None:
    respx.get(f"{JIRA}x").mock(return_value=httpx.Response(502))

    with pytest.raises(UpstreamError):
        await fetcher(jira_client, retries=2).get("x")


@respx.mock
async def test_fetcher_maps_404_and_long_rate_limits(github_client: httpx.AsyncClient) -> None:
    respx.get(f"{GITHUB}missing").mock(return_value=httpx.Response(404))
    reset = int(datetime.now(UTC).timestamp()) + 3600
    respx.get(f"{GITHUB}limited").mock(
        return_value=httpx.Response(
            403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)}
        )
    )

    with pytest.raises(UpstreamNotFoundError):
        await fetcher(github_client).get("missing")
    with pytest.raises(RateLimitedError) as exc:
        await fetcher(github_client).get("limited")
    assert int(exc.value.retry_at.timestamp()) == reset


@respx.mock
async def test_jira_paginates_and_normalizes_issues(jira_client: httpx.AsyncClient) -> None:
    history = jira_history(
        "h1",
        "2026-02-01T10:00:00.000+0000",
        {"field": "Fix Version", "from": None, "to": "100", "toString": "1.0"},
        {"field": "status", "fromString": "Open", "toString": "In Progress"},
        {"field": "Attachment", "toString": "log.txt"},
    )
    pages = [
        {"total": 2, "issues": [jira_issue("K-1", "1", fix_versions=["100"], histories=[history])]},
        {
            "total": 2,
            "issues": [
                jira_issue(
                    "K-2",
                    "2",
                    fix_versions=[],
                    category="done",
                    resolved="2026-02-03T00:00:00.000+0000",
                )
            ],
        },
    ]
    route = respx.get(f"{JIRA}rest/api/2/search").mock(
        side_effect=[httpx.Response(200, json=p) for p in pages]
    )

    tracker = JiraTracker(fetcher(jira_client), page_size=1)
    items = [i async for page in tracker.iter_release_items("DEMO", "100", None) for i in page]

    assert [i.key for i in items] == ["K-1", "K-2"]
    assert route.calls[0].request.url.params["jql"] == (
        "project = DEMO AND fixVersion WAS 100 ORDER BY key ASC"
    )
    assert route.calls[1].request.url.params["startAt"] == "1"
    first = items[0]
    assert first.release_ids == ("100",)
    assert [(e.field, e.to_value) for e in first.events] == [
        (EventField.RELEASE, "100"),
        (EventField.STATUS, "In Progress"),
    ]
    assert items[1].status_category is StatusCategory.DONE
    assert items[1].resolved_at == datetime(2026, 2, 3, tzinfo=UTC)


@respx.mock
async def test_jira_refetches_truncated_changelog(jira_client: httpx.AsyncClient) -> None:
    issue = jira_issue("K-1", "1", fix_versions=["100"], changelog_total=2)
    full = {
        "changelog": {
            "histories": [
                jira_history(
                    "h1",
                    "2026-02-01T10:00:00.000+0000",
                    {"field": "Fix Version", "from": None, "to": "100"},
                ),
            ]
        }
    }
    respx.get(f"{JIRA}rest/api/2/search").mock(
        return_value=httpx.Response(200, json={"total": 1, "issues": [issue]})
    )
    respx.get(f"{JIRA}rest/api/2/issue/1").mock(return_value=httpx.Response(200, json=full))

    tracker = JiraTracker(fetcher(jira_client), page_size=50)
    [page] = [p async for p in tracker.iter_release_items("DEMO", "100", None)]

    assert len(page[0].events) == 1


async def test_jira_rejects_unsafe_identifiers(jira_client: httpx.AsyncClient) -> None:
    tracker = JiraTracker(fetcher(jira_client), page_size=50)

    with pytest.raises(ValueError, match="release id"):
        async for _ in tracker.iter_release_items("DEMO", "1 OR project = SECRET", None):
            pass
    with pytest.raises(ValueError, match="project key"):
        await tracker.list_releases("../admin")


@respx.mock
async def test_github_stops_at_cursor(github_client: httpx.AsyncClient) -> None:
    page = [
        github_pull(3, "K-3: new", updated="2026-03-03T00:00:00Z", merged="2026-03-03T00:00:00Z"),
        github_pull(2, "MINOR: open", updated="2026-03-02T00:00:00Z", state="open"),
        github_pull(1, "K-1: old", updated="2026-02-01T00:00:00Z"),
    ]
    respx.get(f"{GITHUB}repos/apache/demo/pulls").mock(
        return_value=httpx.Response(
            200,
            json=page,
            headers={"link": f'<{GITHUB}repos/apache/demo/pulls?page=2>; rel="next"'},
        )
    )

    host = GitHubCodeHost(fetcher(github_client), GITHUB)
    since = datetime(2026, 3, 1, tzinfo=UTC)
    changes = [c async for p in host.iter_changes("apache/demo", since) for c in p]

    assert [(c.number, c.state) for c in changes] == [
        (3, ChangeState.MERGED),
        (2, ChangeState.OPEN),
    ]


@respx.mock
async def test_github_refuses_pagination_to_foreign_host(github_client: httpx.AsyncClient) -> None:
    respx.get(f"{GITHUB}repos/apache/demo/pulls").mock(
        return_value=httpx.Response(
            200,
            json=[github_pull(1, "K-1", updated="2026-03-03T00:00:00Z")],
            headers={"link": '<https://evil.test/steal>; rel="next"'},
        )
    )
    host = GitHubCodeHost(fetcher(github_client), GITHUB)

    with pytest.raises(UpstreamError, match="unexpected host"):
        async for _ in host.iter_changes("apache/demo", datetime(2026, 1, 1, tzinfo=UTC)):
            pass
