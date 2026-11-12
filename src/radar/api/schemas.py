from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", examples=["kafka"])
    tracker: Literal["jira"] = "jira"
    tracker_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$", examples=["KAFKA"])
    code_host: Literal["github"] = "github"
    repository: str | None = Field(
        default=None,
        description="Code repository to link PRs from; omit for a tracker-only project.",
        pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$",
        examples=["apache/kafka"],
    )


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    tracker: str
    tracker_key: str
    code_host: str | None
    repository: str | None
    created_at: datetime


class ReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    released: bool
    archived: bool
    release_date: date | None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    status: str
    attempts: int
    max_attempts: int
    progress: dict[str, Any]
    last_error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
