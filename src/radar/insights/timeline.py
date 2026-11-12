"""Point-in-time reconstruction of a work item from its event history.

Everything here is pure and operates on one item, so computing a whole release is O(items x
events per item).
"""

from dataclasses import dataclass, field
from datetime import datetime

from radar.connectors.base import EventField


@dataclass(frozen=True, slots=True)
class Event:
    occurred_at: datetime
    field: str
    from_value: str | None
    to_value: str | None


@dataclass(frozen=True, slots=True)
class ItemHistory:
    key: str
    created_at: datetime
    resolved_at: datetime | None
    release_ids: frozenset[str]
    events: tuple[Event, ...] = field(default=())
    title: str = ""


@dataclass(frozen=True, slots=True)
class Interval:
    start: datetime
    end: datetime | None

    def contains(self, at: datetime) -> bool:
        return self.start <= at and (self.end is None or at < self.end)


def membership(item: ItemHistory, release_id: str) -> list[Interval]:
    """Intervals during which the item belonged to the release.

    An item whose first release event is a removal (or that has no release events but is
    currently in the release) was put in the release when it was created.
    """
    changes = sorted(
        (
            e
            for e in item.events
            if e.field == EventField.RELEASE and release_id in (e.from_value, e.to_value)
        ),
        key=lambda e: e.occurred_at,
    )
    starts_member = (
        changes[0].from_value == release_id if changes else release_id in item.release_ids
    )

    intervals: list[Interval] = []
    open_since: datetime | None = item.created_at if starts_member else None
    for change in changes:
        if change.to_value == release_id and open_since is None:
            open_since = change.occurred_at
        elif change.from_value == release_id and open_since is not None:
            intervals.append(Interval(open_since, change.occurred_at))
            open_since = None
    if open_since is not None:
        intervals.append(Interval(open_since, None))
    return intervals


def is_member(intervals: list[Interval], at: datetime) -> bool:
    return any(interval.contains(at) for interval in intervals)


def resolved_as_of(item: ItemHistory, at: datetime) -> datetime | None:
    """When the item was resolved, if it was resolved at `at` (handles reopen/re-resolve)."""
    resolutions = sorted(
        (e for e in item.events if e.field == EventField.RESOLUTION and e.occurred_at <= at),
        key=lambda e: e.occurred_at,
    )
    if resolutions:
        last = resolutions[-1]
        return last.occurred_at if last.to_value else None
    if item.resolved_at is not None and item.resolved_at <= at:
        return item.resolved_at
    return None


def last_activity(item: ItemHistory, at: datetime) -> datetime:
    times = [e.occurred_at for e in item.events if e.occurred_at <= at]
    return max(times, default=item.created_at)
