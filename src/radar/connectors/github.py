import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from radar.connectors.base import ChangeState, CodeChangeRecord
from radar.connectors.errors import UpstreamError
from radar.connectors.http import RetryingFetcher

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
PAGE_SIZE = 100


class GitHubCodeHost:
    """GitHub REST pull requests, newest-updated first, stopping at the incremental cursor."""

    name = "github"

    def __init__(self, fetcher: RetryingFetcher, api_url: str) -> None:
        self._fetcher = fetcher
        self._api_host = httpx.URL(api_url).host

    async def iter_changes(
        self, repository: str, updated_since: datetime
    ) -> AsyncIterator[list[CodeChangeRecord]]:
        if not REPOSITORY_RE.fullmatch(repository):
            raise ValueError(f"invalid repository: {repository!r}")

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
            url = self._next_page(response)
            params = None

    def _next_page(self, response: httpx.Response) -> str | None:
        next_link = response.links.get("next", {}).get("url")
        if next_link is None:
            return None
        # Only follow pagination links back to the configured API host.
        if httpx.URL(next_link).host != self._api_host:
            raise UpstreamError(self.name, "pagination link points to an unexpected host")
        return str(next_link)


def _parse_pull(raw: dict[str, Any]) -> CodeChangeRecord:
    merged_at = _parse(raw.get("merged_at"))
    closed_at = _parse(raw.get("closed_at"))
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
    )


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
