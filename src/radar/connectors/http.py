import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from radar.connectors.errors import RateLimitedError, UpstreamError, UpstreamNotFoundError

log = structlog.get_logger(__name__)

RETRYABLE_STATUS = frozenset({500, 502, 503, 504})


class RetryingFetcher:
    """GET with timeouts, capped exponential backoff with full jitter, and rate-limit awareness.

    Short rate-limit waits are absorbed here; long ones surface as `RateLimitedError` so the
    job queue can reschedule instead of holding a worker.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        source: str,
        max_retries: int,
        *,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._client = client
        self._source = source
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep
        self._jitter = jitter

    async def get(self, url: str, params: Mapping[str, str | int] | None = None) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._client.get(url, params=params)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise UpstreamError(
                        self._source, f"transport error: {type(exc).__name__}"
                    ) from exc
                await self._backoff(attempt, reason=type(exc).__name__)
                attempt += 1
                continue

            if response.is_success:
                return response

            retry_at = _rate_limit_reset(response)
            if retry_at is not None:
                wait = (retry_at - datetime.now(UTC)).total_seconds()
                if wait > self._max_delay or attempt >= self._max_retries:
                    raise RateLimitedError(self._source, retry_at)
                log.warning("upstream_rate_limited", source=self._source, wait_seconds=wait)
                await self._sleep(max(wait, 0.0))
                attempt += 1
                continue

            if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                await self._backoff(attempt, reason=f"http_{response.status_code}")
                attempt += 1
                continue

            if response.status_code == 404:
                raise UpstreamNotFoundError(self._source, "resource not found", 404)
            raise UpstreamError(
                self._source, f"unexpected status {response.status_code}", response.status_code
            )

    async def _backoff(self, attempt: int, *, reason: str) -> None:
        delay = min(self._max_delay, self._base_delay * 2**attempt) * self._jitter()
        log.info("upstream_retry", source=self._source, attempt=attempt + 1, reason=reason)
        await self._sleep(delay)


def _rate_limit_reset(response: httpx.Response) -> datetime | None:
    """Return when the quota resets if this response is a rate-limit rejection."""
    headers = response.headers
    limited = response.status_code == 429 or (
        response.status_code == 403 and headers.get("x-ratelimit-remaining") == "0"
    )
    if not limited:
        return None
    now = datetime.now(UTC)
    if (retry_after := headers.get("retry-after")) and retry_after.isdigit():
        return now + timedelta(seconds=int(retry_after))
    if (reset := headers.get("x-ratelimit-reset")) and reset.isdigit():
        return datetime.fromtimestamp(int(reset), UTC)
    return now + timedelta(seconds=60)
