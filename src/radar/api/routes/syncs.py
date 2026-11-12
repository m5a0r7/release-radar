from typing import Annotated

from fastapi import APIRouter, Path, Response, status
from sqlalchemy import select

from radar.api.deps import ContainerDep, PrincipalDep, ProjectDep, ReleaseDep, SessionDep
from radar.api.errors import ProblemError
from radar.api.schemas import JobOut
from radar.db.models import Job, Project
from radar.jobs import queue
from radar.jobs.queue import SYNC_RELEASE

router = APIRouter(prefix="/v1", tags=["sync"])


@router.post(
    "/projects/{slug}/releases/{release}/syncs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobOut,
    responses={409: {"description": "A sync for this release is already queued or running."}},
)
async def start_sync(
    project: ProjectDep,
    release: ReleaseDep,
    session: SessionDep,
    container: ContainerDep,
    response: Response,
) -> Job:
    """Queue a background sync of the release's work items and the project's code changes."""
    try:
        job = await queue.enqueue(
            session,
            kind=SYNC_RELEASE,
            project_id=project.id,
            payload={"release_id": release.id},
            dedupe_key=f"{SYNC_RELEASE}:{release.id}",
            max_attempts=container.settings.job_max_attempts,
        )
    except queue.JobAlreadyActiveError as exc:
        raise ProblemError(
            409,
            "Sync already in progress",
            f"Job {exc.job.id} is {exc.job.status}.",
            headers={"Location": f"/v1/jobs/{exc.job.id}"},
            extra={"job_id": exc.job.id},
        ) from exc
    response.headers["Location"] = f"/v1/jobs/{job.id}"
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: Annotated[int, Path(ge=1)], session: SessionDep, principal: PrincipalDep
) -> Job:
    job = await session.scalar(
        select(Job)
        .join(Project, Project.id == Job.project_id)
        .where(Job.id == job_id, Project.workspace_id == principal.workspace.id)
    )
    if job is None:
        raise ProblemError(404, "Job not found")
    return job
