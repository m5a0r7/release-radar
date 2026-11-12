"""Checks run while connecting a project, before anything is saved."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from radar.api.deps import ContainerDep, PrincipalDep, SessionDep
from radar.api.schemas import (
    CodeCheck,
    CodeCheckOut,
    RepositoryOut,
    SampleChange,
    TrackerCheck,
    TrackerCheckOut,
)
from radar.db.models import Project
from radar.ingest.linking import extract_item_keys

router = APIRouter(prefix="/v1/connect", tags=["connect"])

CODE_SAMPLE = 100
SHOWN_SAMPLES = 6
UPCOMING_SHOWN = 20


@router.post("/tracker", response_model=TrackerCheckOut)
async def check_tracker(
    body: TrackerCheck, container: ContainerDep, session: SessionDep, principal: PrincipalDep
) -> TrackerCheckOut:
    """Confirm the tracker project exists and list its upcoming releases."""
    tracker = container.connectors.tracker(body.tracker)
    project = await tracker.describe_project(body.tracker_key)
    releases = await tracker.list_releases(body.tracker_key)
    upcoming = [r.name for r in reversed(releases) if not r.released and not r.archived]
    existing = await session.scalar(
        select(Project.slug).where(
            Project.workspace_id == principal.workspace.id,
            Project.tracker == body.tracker,
            Project.tracker_key == body.tracker_key,
        )
    )
    return TrackerCheckOut(
        key=project.key,
        name=project.name,
        upcoming_releases=upcoming[:UPCOMING_SHOWN],
        already_connected_as=existing,
    )


@router.post("/code", response_model=CodeCheckOut)
async def check_code(body: CodeCheck, container: ContainerDep, _: PrincipalDep) -> CodeCheckOut:
    """Sample recent pull requests and report how many reference a ticket of the project."""
    changes = await container.connectors.code_host(body.code_host).recent_changes(
        body.repository, CODE_SAMPLE
    )
    linked = [bool(extract_item_keys(c.title, body.tracker_key)) for c in changes]
    return CodeCheckOut(
        repository=body.repository,
        sampled=len(changes),
        linked=sum(linked),
        linked_share=round(sum(linked) / len(changes), 4) if changes else None,
        samples=[
            SampleChange(number=c.number, title=c.title, linked=is_linked)
            for c, is_linked in list(zip(changes, linked, strict=True))[:SHOWN_SAMPLES]
        ],
    )


@router.get("/repositories", response_model=list[RepositoryOut])
async def search_repositories(
    container: ContainerDep,
    _: PrincipalDep,
    q: Annotated[str, Query(pattern=r"^[A-Za-z0-9._/-]{2,100}$")],
    code_host: Annotated[str, Query(pattern="^github$")] = "github",
) -> list[RepositoryOut]:
    """Public repositories matching a name, or `owner/name`."""
    found = await container.connectors.code_host(code_host).search_repositories(q, limit=6)
    return [RepositoryOut(**asdict(r)) for r in found]
