from datetime import datetime


class UpstreamError(Exception):
    """An upstream API failed in a way retrying will not fix soon."""

    def __init__(self, source: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{source}: {message}")
        self.source = source
        self.status_code = status_code


class UpstreamNotFoundError(UpstreamError):
    pass


class RateLimitedError(UpstreamError):
    """The upstream quota is exhausted; the caller should retry at `retry_at`."""

    def __init__(self, source: str, retry_at: datetime) -> None:
        super().__init__(source, f"rate limited until {retry_at.isoformat()}", 429)
        self.retry_at = retry_at
