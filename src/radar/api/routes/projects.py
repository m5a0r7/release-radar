from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from radar.api.deps import ContainerDep, ProjectDep, SessionDep
from radar.api.errors import ProblemError
from radar.api.schemas import ProjectCreate, ProjectOut, ReleaseOut
from radar.db.models import Project, Release

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectOut)
async def create_project(
    body: ProjectCreate, session: SessionDep, container: ContainerDep, response: Response
) -> Project:
    """Track a project. Its releases are fetched immediately, which also validates the key."""
    project = Project(
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
        raise ProblemError(409, "Project already exists", "Slug or tracker key is taken.") from exc

    await container.sync.refresh_releases(session, project)
    response.headers["Location"] = f"/v1/projects/{project.slug}"
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(session: SessionDep) -> list[Project]:
    return list(await session.scalars(select(Project).order_by(Project.slug)))


@router.get("/{slug}", response_model=ProjectOut)
async def get_project(project: ProjectDep) -> Project:
    return project


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
