import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from radar.connectors.base import ChangeState, CodeChangeRecord, RepositoryRecord
from radar.connectors.errors import UpstreamError
from radar.connectors.http import RetryingFetcher

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
SEARCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
PAGE_SIZE = 100
# Only scanned for issue references; long bodies are mostly logs and templates.
MAX_BODY_CHARS = 20_000


class GitHubCodeHost:
    """GitHub REST pull requests, newest-updated first, stopping at the incremental cursor."""

    name = "github"

    def __init__(self, fetcher: RetryingFetcher, api_url: str) -> None:
        self._fetcher = fetcher
        self._api_host = httpx.URL(api_url).host

    async def recent_changes(self, repository: str, limit: int) -> list[CodeChangeRecord]:
        require_repository(repository)
        response = await self._fetcher.get(
            f"repos/{repository}/pulls",
            params={"state": "all", "sort": "created", "direction": "desc", "per_page": limit},
        )
        return [_parse_pull(raw) for raw in response.json()]

    async def search_repositories(self, query: str, limit: int) -> list[RepositoryRecord]:
        if not SEARCH_RE.fullmatch(query):
            raise ValueError(f"invalid repository search: {query!r}")
        owner, _, name = query.rpartition("/")
        terms = f"{name} in:name user:{owner}" if owner else f"{name} in:name"
        response = await self._fetcher.get(
            "search/repositories", params={"q": terms, "per_page": limit, "sort": "stars"}
        )
        return [
            RepositoryRecord(
                full_name=raw["full_name"],
                description=raw.get("description"),
                language=raw.get("language"),
                stars=int(raw.get("stargazers_count", 0)),
                pushed_at=parse_time(raw.get("pushed_at")),
            )
            for raw in response.json().get("items", [])
            if not raw.get("private")
        ]

    async def iter_changes(
        self, repository: str, updated_since: datetime
    ) -> AsyncIterator[list[CodeChangeRecord]]:
        require_repository(repository)

        url: str | None = f"repos/{repository}/pulls"
        params: dict[str, str | int] | None = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": PAGE_SIZE,
        }
        while url is not None:
            response = await self._fetcher.get(url, params=params)
            page = [_parse_pull(raw) for raw in response.json()]
            fresh = [change for change in page if change.updated_at >= updated_since]
            if fresh:
                yield fresh
            if len(fresh) < len(page):
                return
            url = next_page(response, self._api_host)
            params = None


def next_page(response: httpx.Response, api_host: str) -> str | None:
    next_link = response.links.get("next", {}).get("url")
    if next_link is None:
        return None
    # Only follow pagination links back to the configured API host.
    if httpx.URL(next_link).host != api_host:
        raise UpstreamError("github", "pagination link points to an unexpected host")
    return str(next_link)


def require_repository(repository: str) -> None:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ValueError(f"invalid repository: {repository!r}")


def _parse_pull(raw: dict[str, Any]) -> CodeChangeRecord:
    merged_at = parse_time(raw.get("merged_at"))
    closed_at = parse_time(raw.get("closed_at"))
    if merged_at is not None:
        state = ChangeState.MERGED
    elif raw.get("state") == "closed":
        state = ChangeState.CLOSED
    else:
        state = ChangeState.OPEN
    return CodeChangeRecord(
        external_id=str(raw["id"]),
        number=int(raw["number"]),
        title=raw.get("title") or "",
        author=(raw.get("user") or {}).get("login"),
        state=state,
        url=raw["html_url"],
        created_at=datetime.fromisoformat(raw["created_at"]),
        updated_at=datetime.fromisoformat(raw["updated_at"]),
        merged_at=merged_at,
        closed_at=closed_at,
        body=(raw.get("body") or "")[:MAX_BODY_CHARS],
    )


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
