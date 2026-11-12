import hashlib
from datetime import timedelta

import anyio
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from radar.api.deps import ContainerDep, PeriodDep, ProjectDep, ReleaseDep, SessionDep
from radar.db.models import Project, Release
from radar.insights.drift import compute_drift
from radar.insights.repository import load_drift_inputs
from radar.insights.schemas import DriftReport
from radar.narrative.schemas import NarrativeResponse

router = APIRouter(prefix="/v1/projects/{slug}/releases/{release}", tags=["insights"])

# Revalidate every time (cheap, thanks to the ETag) so a finished sync shows up immediately.
CACHE_CONTROL = "private, no-cache"


async def _report(
    session: SessionDep,
    container: ContainerDep,
    project: Project,
    release: Release,
    period: PeriodDep,
) -> DriftReport:
    # Data refreshed by the background schedule counts as current, plus slack for the sync itself.
    stale_after = timedelta(hours=container.settings.auto_sync_hours + 1)
    inputs = await load_drift_inputs(
        session, project, release, period.start, period.end, period.target_date, stale_after
    )
    # The Monte Carlo forecast is CPU-bound; keep it off the event loop.
    return await anyio.to_thread.run_sync(compute_drift, inputs)


def _conditional(request: Request, model: BaseModel) -> Response:
    body = model.model_dump_json().encode()
    etag = f'"{hashlib.sha256(body).hexdigest()[:32]}"'
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


@router.get("/drift", response_model=DriftReport)
async def get_drift(
    request: Request,
    project: ProjectDep,
    release: ReleaseDep,
    period: PeriodDep,
    session: SessionDep,
    container: ContainerDep,
) -> Response:
    """Plan-vs-actual metrics for a release over a period, computed from synced data."""
    report = await _report(session, container, project, release, period)
    return _conditional(request, report)


@router.get("/narrative", response_model=NarrativeResponse)
async def get_narrative(
    request: Request,
    project: ProjectDep,
    release: ReleaseDep,
    period: PeriodDep,
    session: SessionDep,
    container: ContainerDep,
    refresh: bool = False,
) -> Response:
    """LLM explanation of the drift: findings, hypotheses, calibrated confidence and evidence."""
    report = await _report(session, container, project, release, period)
    narrative = await container.narratives.narrate(session, report, refresh=refresh)
    return _conditional(request, narrative)
