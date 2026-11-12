from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.api.errors import ProblemError
from radar.container import Container
from radar.db.models import Project, Release

DEFAULT_PERIOD_DAYS = 56


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as session, session.begin():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SlugPath = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
ReleasePath = Annotated[str, Path(min_length=1, max_length=255)]


async def get_project(slug: SlugPath, session: SessionDep) -> Project:
    project = await session.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise ProblemError(404, "Project not found", f"No project with slug '{slug}'.")
    return project


ProjectDep = Annotated[Project, Depends(get_project)]


async def get_release(project: ProjectDep, release: ReleasePath, session: SessionDep) -> Release:
    found = await session.scalar(
        select(Release).where(Release.project_id == project.id, Release.name == release)
    )
    if found is None:
        raise ProblemError(
            404, "Release not found", f"Project '{project.slug}' has no release '{release}'."
        )
    return found


ReleaseDep = Annotated[Release, Depends(get_release)]


class PeriodParams:
    def __init__(
        self,
        container: ContainerDep,
        start: Annotated[
            date | None, Query(alias="from", description="Inclusive start date (UTC).")
        ] = None,
        end: Annotated[
            date | None, Query(alias="to", description="Inclusive end date (UTC).")
        ] = None,
        target_date: Annotated[
            date | None, Query(description="Overrides the tracker's release date.")
        ] = None,
    ) -> None:
        today = datetime.now(UTC).date()
        self.end = end or today
        self.start = start or self.end - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
        self.target_date = target_date
        max_days = container.settings.max_period_days
        if self.start > self.end:
            raise ProblemError(422, "Invalid period", "'from' must be on or before 'to'.")
        if self.end > today:
            raise ProblemError(422, "Invalid period", "'to' cannot be in the future.")
        if (self.end - self.start).days + 1 > max_days:
            raise ProblemError(422, "Invalid period", f"The period cannot exceed {max_days} days.")


PeriodDep = Annotated[PeriodParams, Depends()]
