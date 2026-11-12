from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import BigInteger, select
from sqlalchemy.exc import IntegrityError

from radar.api.deps import (
    ContainerDep,
    PrincipalDep,
    ProjectDep,
    ReleaseDep,
    SessionDep,
)
from radar.api.errors import ProblemError
from radar.api.schemas import (
    ProjectCreate,
    ProjectOut,
    ReleaseOut,
    ReleaseUpdate,
    TrackedReleaseOut,
)
from radar.container import Container
from radar.db.models import Job, Project, Release
from radar.jobs.queue import SUCCEEDED, SYNC_RELEASE

router = APIRouter(prefix="/v1/projects", tags=["projects"])


async def _tracked(
    session: SessionDep, project_ids: Sequence[int]
) -> dict[int, list[TrackedReleaseOut]]:
    """Releases with at least one sync job, with their latest sync status, per project."""
    release_id = Job.payload["release_id"].astext.cast(BigInteger)
    rows = await session.execute(
        select(Release, Job.status, Job.finished_at)
        .join(Job, release_id == Release.id)
        .where(Job.kind == SYNC_RELEASE, Release.project_id.in_(project_ids))
        .order_by(Release.project_id, Release.id.desc(), Job.id.desc())
    )
    tracked: dict[int, list[TrackedReleaseOut]] = {pid: [] for pid in project_ids}
    seen: dict[int, TrackedReleaseOut] = {}
    for release, job_status, finished_at in rows:
        entry = seen.get(release.id)
        if entry is None:
            entry = TrackedReleaseOut(
                name=release.name,
                released=release.released,
                target_date=release.target_date,
                last_synced_at=None,
                sync_status=job_status,
            )
            seen[release.id] = entry
            tracked[release.project_id].append(entry)
        if job_status == SUCCEEDED and entry.last_synced_at is None:
            entry.last_synced_at = finished_at
    return tracked


def _out(project: Project, container: Container, tracked: list[TrackedReleaseOut]) -> ProjectOut:
    tracker = container.connectors.tracker(project.tracker)
    return ProjectOut(
        slug=project.slug,
        tracker=project.tracker,
        tracker_key=project.tracker_key,
        code_host=project.code_host,
        repository=project.repository,
        created_at=project.created_at,
        item_url_template=tracker.item_url_template,
        search_url_template=tracker.search_url_template,
        tracked_releases=tracked,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectOut)
async def create_project(
    body: ProjectCreate,
    session: SessionDep,
    container: ContainerDep,
    principal: PrincipalDep,
    response: Response,
) -> ProjectOut:
    """Track a project. Its releases are fetched immediately, which also validates the key."""
    project = Project(
        workspace_id=principal.workspace.id,
        slug=body.slug,
        tracker=body.tracker,
        tracker_key=body.tracker_key,
        code_host=body.code_host if body.repository else None,
        repository=body.repository,
    )
    session.add(project)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ProblemError(
            409, "Project already exists", "This workspace already uses that name or Jira key."
        ) from exc

    await container.sync.refresh_releases(session, project)
    await session.refresh(project)
    response.headers["Location"] = f"/v1/projects/{project.slug}"
    return _out(project, container, [])


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    session: SessionDep, container: ContainerDep, principal: PrincipalDep
) -> list[ProjectOut]:
    projects = list(
        await session.scalars(
            select(Project)
            .where(Project.workspace_id == principal.workspace.id)
            .order_by(Project.slug)
        )
    )
    tracked = await _tracked(session, [p.id for p in projects])
    return [_out(p, container, tracked[p.id]) for p in projects]


@router.get("/{slug}", response_model=ProjectOut)
async def get_project(
    project: ProjectDep, session: SessionDep, container: ContainerDep
) -> ProjectOut:
    tracked = await _tracked(session, [project.id])
    return _out(project, container, tracked[project.id])


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project: ProjectDep, session: SessionDep) -> None:
    """Stop tracking a project and delete its synced data."""
    await session.delete(project)


@router.get("/{slug}/releases", response_model=list[ReleaseOut])
async def list_releases(
    project: ProjectDep,
    session: SessionDep,
    released: Annotated[bool | None, Query()] = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Release]:
    query = select(Release).where(Release.project_id == project.id)
    if released is not None:
        query = query.where(Release.released == released)
    if not include_archived:
        query = query.where(Release.archived.is_(False))
    # Releases are inserted in tracker order (oldest first), so newest first is id descending.
    query = query.order_by(Release.id.desc()).limit(limit)
    return list(await session.scalars(query))


@router.patch("/{slug}/releases/{release}", response_model=ReleaseOut)
async def update_release(release: ReleaseDep, body: ReleaseUpdate) -> Release:
    """Set the date the team is aiming for, used as the forecast target."""
    release.target_date = body.target_date
    return release
