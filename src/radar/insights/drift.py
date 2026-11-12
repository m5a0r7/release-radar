"""Release drift metrics. Pure functions over loaded history; no I/O.

Period semantics: `start` and `end` are dates in UTC, `end` inclusive. Internally the window is
the half-open datetime range [start 00:00, end+1 00:00).
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from radar.insights.forecast import monte_carlo_completion
from radar.insights.schemas import (
    CodeMetrics,
    Coverage,
    DriftReport,
    DriftStatus,
    ForecastMetrics,
    IdleMetrics,
    Period,
    PlanningMetrics,
    ProgressMetrics,
    ReleaseSummary,
    ScopeMetrics,
    ThroughputMetrics,
    WeeklyThroughput,
)
from radar.insights.timeline import (
    Interval,
    ItemHistory,
    is_member,
    last_activity,
    membership,
    resolved_as_of,
)

IDLE_THRESHOLD = timedelta(days=14)
LATE_TAG_WINDOW = timedelta(hours=24)
ANOMALY_MIN_WEEKS = 6
ANOMALY_Z = 3.5
SAMPLE_KEYS = 10


@dataclass(frozen=True, slots=True)
class ChangeHistory:
    number: int
    linked_keys: tuple[str, ...]
    merged_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DriftInputs:
    project: str
    release: ReleaseSummary
    release_external_id: str
    items: Sequence[ItemHistory]
    linked_changes: Sequence[ChangeHistory]
    code_available: bool
    project_merged_in_period: int
    project_unlinked_merged_in_period: int
    coverage: Coverage
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class _Item:
    history: ItemHistory
    intervals: list[Interval]


def compute_drift(inputs: DriftInputs) -> DriftReport:
    start_at = _midnight(inputs.start)
    end_at = _midnight(inputs.end + timedelta(days=1))
    length = end_at - start_at

    items = [_Item(h, membership(h, inputs.release_external_id)) for h in inputs.items]
    at_end = [i for i in items if is_member(i.intervals, end_at)]
    at_start = [i for i in items if is_member(i.intervals, start_at)]

    scope = _scope(items, at_start, at_end, start_at, end_at)
    completed = _completed(at_end, start_at, end_at)
    previous = _completed(
        [i for i in items if is_member(i.intervals, start_at)], start_at - length, start_at
    )
    open_at_end = [i for i in at_end if resolved_as_of(i.history, end_at) is None]

    progress = ProgressMetrics(
        completed_in_period=len(completed),
        completed_previous_period=len(previous),
        open_at_end=len(open_at_end),
        done_at_end=len(at_end) - len(open_at_end),
        percent_complete=_pct(len(at_end) - len(open_at_end), len(at_end)),
    )
    planning = _planning(completed, end_at)
    idle = _idle(open_at_end, inputs.linked_changes, end_at)
    throughput = _throughput(completed, inputs.start, inputs.end)
    forecast = _forecast(len(open_at_end), throughput, inputs.end, inputs.release.target_date)
    code = _code(inputs, open_at_end, start_at, end_at)

    return DriftReport(
        project=inputs.project,
        release=inputs.release,
        period=Period(start=inputs.start, end=inputs.end, days=length.days),
        status=_status(scope, idle, forecast, len(at_end)),
        scope=scope,
        progress=progress,
        planning=planning,
        idle=idle,
        throughput=throughput,
        forecast=forecast,
        code=code,
        coverage=inputs.coverage,
    )


def _scope(
    items: list[_Item],
    at_start: list[_Item],
    at_end: list[_Item],
    start_at: datetime,
    end_at: datetime,
) -> ScopeMetrics:
    added = sorted(
        i.history.key for i in items if any(start_at < iv.start < end_at for iv in i.intervals)
    )
    removed = sorted(
        i.history.key
        for i in items
        if any(iv.end is not None and start_at <= iv.end < end_at for iv in i.intervals)
    )
    return ScopeMetrics(
        at_start=len(at_start),
        at_end=len(at_end),
        added=len(added),
        removed=len(removed),
        change_pct=_pct(len(at_end) - len(at_start), len(at_start)),
        added_keys=added[:SAMPLE_KEYS],
        removed_keys=removed[:SAMPLE_KEYS],
    )


def _completed(members: list[_Item], start_at: datetime, end_at: datetime) -> list[_Item]:
    """Members at the window end whose resolution (as of then) falls inside the window."""
    done = []
    for item in members:
        resolved = resolved_as_of(item.history, end_at - timedelta(microseconds=1))
        if resolved is not None and start_at <= resolved < end_at:
            done.append(item)
    return done


def _planning(completed: list[_Item], end_at: datetime) -> PlanningMetrics:
    late = sorted(
        item.history.key
        for item in completed
        if (resolved := resolved_as_of(item.history, end_at)) is not None
        and item.intervals
        and item.intervals[-1].start >= resolved - LATE_TAG_WINDOW
        and item.intervals[-1].start > item.history.created_at
    )
    return PlanningMetrics(
        window_hours=int(LATE_TAG_WINDOW.total_seconds() // 3600),
        completed_in_period=len(completed),
        tagged_at_resolution=len(late),
        unplanned_share=_ratio(len(late), len(completed)),
        sample_keys=late[:SAMPLE_KEYS],
    )


def _idle(
    open_items: list[_Item], changes: Sequence[ChangeHistory], end_at: datetime
) -> IdleMetrics:
    latest_change: dict[str, datetime] = {}
    for change in changes:
        if change.updated_at > end_at:
            continue
        for key in change.linked_keys:
            if key not in latest_change or change.updated_at > latest_change[key]:
                latest_change[key] = change.updated_at

    idle = sorted(
        item.history.key
        for item in open_items
        if max(
            last_activity(item.history, end_at),
            latest_change.get(item.history.key, item.history.created_at),
        )
        < end_at - IDLE_THRESHOLD
    )
    return IdleMetrics(
        threshold_days=IDLE_THRESHOLD.days,
        open_items=len(open_items),
        idle_items=len(idle),
        idle_share=_ratio(len(idle), len(open_items)),
        idle_keys=idle[:SAMPLE_KEYS],
    )


def _throughput(completed: list[_Item], start: date, end: date) -> ThroughputMetrics:
    buckets: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        buckets.append((cursor, min(cursor + timedelta(days=6), end)))
        cursor += timedelta(days=7)

    counts = [0] * len(buckets)
    end_at = _midnight(end + timedelta(days=1))
    for item in completed:
        resolved = resolved_as_of(item.history, end_at)
        if resolved is not None:
            counts[min((resolved.date() - start).days // 7, len(buckets) - 1)] += 1

    full = [(b[1] - b[0]).days == 6 for b in buckets]
    full_counts = [c for c, f in zip(counts, full, strict=True) if f]
    flags = _anomalies(full_counts)
    flag_iter = iter(flags)
    return ThroughputMetrics(
        weekly=[
            WeeklyThroughput(
                start=b[0],
                end=b[1],
                completed=c,
                full_week=f,
                anomaly=next(flag_iter) if f else False,
            )
            for b, c, f in zip(buckets, counts, full, strict=True)
        ],
        mean_per_full_week=round(statistics.fmean(full_counts), 2) if full_counts else None,
    )


def _anomalies(values: list[int]) -> list[bool]:
    """Modified z-score (median / MAD) so one bad week cannot hide itself by moving the mean."""
    if len(values) < ANOMALY_MIN_WEEKS:
        return [False] * len(values)
    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)
    if mad == 0:
        mean_ad = statistics.fmean(abs(v - median) for v in values)
        scale = 1.253314 * mean_ad
    else:
        scale = 1.4826 * mad
    if scale == 0:
        return [False] * len(values)
    return [abs(v - median) / scale > ANOMALY_Z for v in values]


def _forecast(
    remaining: int, throughput: ThroughputMetrics, end: date, target: date | None
) -> ForecastMetrics:
    samples = [w.completed for w in throughput.weekly if w.full_week]
    result = monte_carlo_completion(remaining, samples, end, target)
    slip = (result.p50_date - target).days if result.p50_date and target else None
    return ForecastMetrics(
        remaining=remaining,
        p50_date=result.p50_date,
        p85_date=result.p85_date,
        target_date=target,
        on_time_probability=result.on_time_probability,
        slip_days_p50=slip,
    )


def _code(
    inputs: DriftInputs, open_items: list[_Item], start_at: datetime, end_at: datetime
) -> CodeMetrics:
    release_keys = {item.key for item in inputs.items}
    merged_by_key: set[str] = set()
    linked_merged = 0
    for change in inputs.linked_changes:
        if change.merged_at is None or change.merged_at >= end_at:
            continue
        keys = release_keys.intersection(change.linked_keys)
        merged_by_key |= keys
        if keys and change.merged_at >= start_at:
            linked_merged += 1

    code_done = sorted(i.history.key for i in open_items if i.history.key in merged_by_key)
    return CodeMetrics(
        available=inputs.code_available,
        linked_merged_in_period=linked_merged,
        project_merged_in_period=inputs.project_merged_in_period,
        unlinked_merged_in_period=inputs.project_unlinked_merged_in_period,
        unlinked_share=_ratio(
            inputs.project_unlinked_merged_in_period, inputs.project_merged_in_period
        ),
        open_items_with_merged_change=len(code_done),
        sample_keys=code_done[:SAMPLE_KEYS],
    )


def _status(
    scope: ScopeMetrics, idle: IdleMetrics, forecast: ForecastMetrics, members: int
) -> DriftStatus:
    if members == 0:
        return DriftStatus.INSUFFICIENT_DATA
    if forecast.on_time_probability is not None:
        if forecast.on_time_probability >= 0.7:
            return DriftStatus.ON_TRACK
        return DriftStatus.AT_RISK if forecast.on_time_probability >= 0.4 else DriftStatus.OFF_TRACK
    if forecast.remaining > 0 and forecast.p50_date is None:
        return DriftStatus.OFF_TRACK
    churn = abs(scope.change_pct or 0.0)
    if churn > 25 or (idle.idle_share or 0.0) > 0.3:
        return DriftStatus.AT_RISK
    return DriftStatus.ON_TRACK


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None
