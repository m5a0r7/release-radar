from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DriftStatus(StrEnum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"
    INSUFFICIENT_DATA = "insufficient_data"


class Period(BaseModel):
    start: date
    end: date = Field(description="Inclusive.")
    days: int


class ReleaseSummary(BaseModel):
    id: int
    name: str
    released: bool
    release_date: date | None
    target_date: date | None = Field(description="Query override, else the tracker release date.")


class ScopeMetrics(BaseModel):
    at_start: int
    at_end: int
    added: int
    removed: int
    change_pct: float | None = Field(description="Net scope change relative to the start, in %.")
    added_keys: list[str]
    removed_keys: list[str]


class ProgressMetrics(BaseModel):
    completed_in_period: int
    completed_previous_period: int
    open_at_end: int
    done_at_end: int
    percent_complete: float | None


class PlanningMetrics(BaseModel):
    window_hours: int
    completed_in_period: int
    tagged_at_resolution: int = Field(
        description="Completed items added to the release within `window_hours` of resolution."
    )
    unplanned_share: float | None
    sample_keys: list[str]


class IdleMetrics(BaseModel):
    threshold_days: int
    open_items: int
    idle_items: int
    idle_share: float | None
    idle_keys: list[str]


class WeeklyThroughput(BaseModel):
    start: date
    end: date
    completed: int
    full_week: bool
    anomaly: bool


class ThroughputMetrics(BaseModel):
    weekly: list[WeeklyThroughput]
    mean_per_full_week: float | None


class ForecastMetrics(BaseModel):
    method: str = "monte_carlo_bootstrap"
    remaining: int
    p50_date: date | None
    p85_date: date | None
    target_date: date | None
    on_time_probability: float | None
    slip_days_p50: int | None


class CodeMetrics(BaseModel):
    available: bool
    linked_merged_in_period: int
    project_merged_in_period: int
    unlinked_merged_in_period: int
    unlinked_share: float | None
    open_items_with_merged_change: int
    sample_keys: list[str]


class Coverage(BaseModel):
    work_items_synced_at: datetime | None
    code_changes_synced_from: datetime | None
    code_changes_synced_at: datetime | None
    complete: bool
    notes: list[str]


class DriftReport(BaseModel):
    project: str
    release: ReleaseSummary
    period: Period
    status: DriftStatus
    scope: ScopeMetrics
    progress: ProgressMetrics
    planning: PlanningMetrics
    idle: IdleMetrics
    throughput: ThroughputMetrics
    forecast: ForecastMetrics
    code: CodeMetrics
    coverage: Coverage
