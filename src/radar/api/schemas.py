from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

REPOSITORY_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
TRACKER_KEY_PATTERN = r"^[A-Z][A-Z0-9_]{1,31}$"


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", examples=["kafka"])
    tracker: Literal["jira"] = "jira"
    tracker_key: str = Field(pattern=TRACKER_KEY_PATTERN, examples=["KAFKA"])
    code_host: Literal["github"] = "github"
    repository: str | None = Field(
        default=None,
        description="Code repository to link PRs from; omit for a tracker-only project.",
        pattern=REPOSITORY_PATTERN,
        examples=["apache/kafka"],
    )


class TrackedReleaseOut(BaseModel):
    """A release that has been synced at least once."""

    name: str
    released: bool
    target_date: date | None
    last_synced_at: datetime | None
    sync_status: str = Field(description="Status of the latest sync job.")


class ProjectOut(BaseModel):
    slug: str
    tracker: str
    tracker_key: str
    code_host: str | None
    repository: str | None
    created_at: datetime
    item_url_template: str = Field(
        description="Browser URL of a work item, with `{key}` as the placeholder.",
        examples=["https://issues.apache.org/jira/browse/{key}"],
    )
    search_url_template: str = Field(
        description="Browser URL listing work items, with `{keys}` as a comma-separated list."
    )
    tracked_releases: list[TrackedReleaseOut]


class ReleaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    released: bool
    archived: bool
    release_date: date | None
    target_date: date | None


class ReleaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_date: date | None = Field(description="Forecast target; null falls back to Jira.")


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


class AuthConfigOut(BaseModel):
    github: bool
    demo: bool


class UserOut(BaseModel):
    name: str
    email: str | None
    avatar_url: str | None
    provider: str


class WorkspaceOut(BaseModel):
    id: int
    name: str


class MeOut(BaseModel):
    user: UserOut
    workspace: WorkspaceOut


class TrackerCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracker: Literal["jira"] = "jira"
    tracker_key: str = Field(pattern=TRACKER_KEY_PATTERN)


class TrackerCheckOut(BaseModel):
    key: str
    name: str
    upcoming_releases: list[str] = Field(description="Unreleased, unarchived; newest first.")
    already_connected_as: str | None = Field(description="Slug, if this workspace tracks it.")


class CodeCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code_host: Literal["github"] = "github"
    repository: str = Field(pattern=REPOSITORY_PATTERN)
    tracker_key: str = Field(pattern=TRACKER_KEY_PATTERN)


class SampleChange(BaseModel):
    number: int
    title: str
    linked: bool


class CodeCheckOut(BaseModel):
    repository: str
    sampled: int
    linked: int
    linked_share: float | None
    samples: list[SampleChange]


class RepositoryOut(BaseModel):
    full_name: str
    description: str | None
    language: str | None
    stars: int
    pushed_at: datetime | None
