"""RFC 9457 problem+json responses for every error path."""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from radar.connectors.errors import RateLimitedError, UpstreamError, UpstreamNotFoundError

log = structlog.get_logger(__name__)

PROBLEM_JSON = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.title = title
        self.detail = detail
        self.headers = headers
        self.extra = extra or {}


def problem(
    request: Request,
    status: int,
    title: str,
    detail: str | None = None,
    *,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body["instance"] = request.url.path
    if request_id := getattr(request.state, "request_id", None):
        body["request_id"] = request_id
    body.update(extra)
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_JSON)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem(request, exc.status, exc.title, exc.detail, headers=exc.headers, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem(request, 422, "Invalid request", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RateLimitedError)
    async def _rate_limited(request: Request, exc: RateLimitedError) -> JSONResponse:
        retry_after = max(1, int((exc.retry_at - datetime.now(UTC)).total_seconds()))
        return problem(
            request,
            503,
            "Upstream rate limit reached",
            f"{exc.source} quota is exhausted; retry later.",
            headers={"Retry-After": str(retry_after)},
        )

    @app.exception_handler(UpstreamNotFoundError)
    async def _upstream_not_found(request: Request, exc: UpstreamNotFoundError) -> JSONResponse:
        return problem(request, 422, "Upstream resource not found", str(exc))

    @app.exception_handler(UpstreamError)
    async def _upstream(request: Request, exc: UpstreamError) -> JSONResponse:
        log.warning("upstream_error", source=exc.source, status_code=exc.status_code)
        return problem(request, 502, "Upstream service error", f"{exc.source} request failed.")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error")
        return problem(request, 500, "Internal server error")
