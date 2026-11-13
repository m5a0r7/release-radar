import re
from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPOSITORY_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
TRACKER_KEY_PATTERN = r"^[A-Z][A-Z0-9_]{1,31}$"
TRACKER_KEY_PATTERNS = {"jira": TRACKER_KEY_PATTERN, "github": REPOSITORY_PATTERN}
Tracker = Literal["jira", "github"]
TrackerKey = Annotated[
    str,
    Field(
        min_length=2,
        max_length=140,
        description="Jira project key (`KAFKA`), or `owner/name` for GitHub Issues.",
        examples=["KAFKA", "apache/arrow"],
    ),
]


class TrackerKeyed(BaseModel):
    """Validates `tracker_key` against the format of the chosen tracker."""

    tracker: Tracker = "jira"
    tracker_key: TrackerKey

    @model_validator(mode="after")
    def _check_tracker_key(self) -> Self:
        if not re.fullmatch(TRACKER_KEY_PATTERNS[self.tracker], self.tracker_key):
            expected = (
                "an uppercase Jira key like KAFKA" if self.tracker == "jira" else "owner/name"
            )
            raise ValueError(f"tracker_key must be {expected}")
        return self


class ProjectCreate(TrackerKeyed):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", examples=["kafka"])
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
    sync_job_id: int | None = None
    sync_progress: dict[str, Any] = Field(
        default_factory=dict, description="Latest sync progress, updated as each batch is saved."
    )
    sync_error: str | None = Field(
        default=None, description="Why the latest sync is waiting or failed, when known."
    )


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
    demo_until: date | None = Field(description="Last day of a time-boxed public demo.")


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


class TrackerCheck(TrackerKeyed):
    model_config = ConfigDict(extra="forbid")


class TrackerCheckOut(BaseModel):
    key: str
    name: str
    upcoming_releases: list[str] = Field(description="Unreleased, unarchived; newest first.")
    already_connected_as: str | None = Field(description="Slug, if this workspace tracks it.")


class CodeCheck(TrackerKeyed):
    model_config = ConfigDict(extra="forbid")

    code_host: Literal["github"] = "github"
    repository: str = Field(pattern=REPOSITORY_PATTERN)


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
