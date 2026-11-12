"""Flattens a drift report into numbered facts the LLM must cite.

Every number the narrative may use lives here with a stable id, a unit and the work-item keys
behind it, which is what makes the evidence chain verifiable.
"""

from datetime import date

from pydantic import BaseModel

from radar.insights.schemas import DriftReport


class Evidence(BaseModel):
    id: str
    metric: str
    value: float | int | str | None
    unit: str
    description: str
    keys: list[str] = []


def build_evidence(report: DriftReport) -> list[Evidence]:
    s, p, pl, idle, f, c = (
        report.scope,
        report.progress,
        report.planning,
        report.idle,
        report.forecast,
        report.code,
    )
    facts: list[tuple[str, float | int | str | None, str, str, list[str]]] = [
        ("scope.at_start", s.at_start, "items", "Items in the release at period start", []),
        ("scope.at_end", s.at_end, "items", "Items in the release at period end", []),
        (
            "scope.added",
            s.added,
            "items",
            "Items added to the release during the period",
            s.added_keys,
        ),
        (
            "scope.removed",
            s.removed,
            "items",
            "Items removed from the release during the period",
            s.removed_keys,
        ),
        ("scope.change_pct", s.change_pct, "%", "Net scope change versus period start", []),
        (
            "progress.completed",
            p.completed_in_period,
            "items",
            "Release items resolved during the period",
            [],
        ),
        (
            "progress.completed_previous",
            p.completed_previous_period,
            "items",
            "Release items resolved in the preceding period of equal length",
            [],
        ),
        (
            "progress.open_at_end",
            p.open_at_end,
            "items",
            "Unresolved release items at period end",
            [],
        ),
        (
            "progress.percent_complete",
            p.percent_complete,
            "%",
            "Share of release items resolved at period end",
            [],
        ),
        (
            "planning.tagged_at_resolution",
            pl.tagged_at_resolution,
            "items",
            "Completed items only added to the release close to resolution (unplanned)",
            pl.sample_keys,
        ),
        (
            "planning.unplanned_share",
            _pct(pl.unplanned_share),
            "%",
            "Share of completed items that were unplanned",
            [],
        ),
        (
            "planning.window_hours",
            pl.window_hours,
            "hours",
            "An item added to the release this close to its resolution counts as unplanned",
            [],
        ),
        (
            "idle.threshold_days",
            idle.threshold_days,
            "days",
            "Days without activity after which an open item counts as idle",
            [],
        ),
        (
            "idle.items",
            idle.idle_items,
            "items",
            f"Open items with no activity for {idle.threshold_days}+ days",
            idle.idle_keys,
        ),
        ("idle.share", _pct(idle.idle_share), "%", "Share of open items that are idle", []),
        (
            "throughput.mean_per_week",
            report.throughput.mean_per_full_week,
            "items/week",
            "Mean items resolved per full week in the period",
            [],
        ),
    ]
    facts += [
        (
            f"throughput.week_{w.start.isoformat()}",
            w.completed,
            "items",
            f"Items resolved {w.start.isoformat()}..{w.end.isoformat()}"
            + (" (statistical anomaly)" if w.anomaly else ""),
            [],
        )
        for w in report.throughput.weekly
    ]
    facts += [
        ("forecast.remaining", f.remaining, "items", "Items left to resolve", []),
        ("forecast.p50_date", _iso(f.p50_date), "date", "Median projected completion date", []),
        ("forecast.p85_date", _iso(f.p85_date), "date", "85th percentile completion date", []),
        ("forecast.target_date", _iso(f.target_date), "date", "Target release date", []),
        (
            "forecast.on_time_probability",
            _pct(f.on_time_probability),
            "%",
            "Probability of finishing by the target date",
            [],
        ),
        (
            "forecast.slip_days_p50",
            f.slip_days_p50,
            "days",
            "Median projected slip past the target date",
            [],
        ),
    ]
    if c.available:
        facts += [
            (
                "code.linked_merged",
                c.linked_merged_in_period,
                "PRs",
                "Merged PRs referencing release items during the period",
                [],
            ),
            (
                "code.project_merged",
                c.project_merged_in_period,
                "PRs",
                "All PRs merged in the repository during the period",
                [],
            ),
            (
                "code.unlinked_share",
                _pct(c.unlinked_share),
                "%",
                "Share of merged PRs that reference no tracker item",
                [],
            ),
            (
                "code.open_items_with_merged_change",
                c.open_items_with_merged_change,
                "items",
                "Open release items whose linked PR is already merged (status lag)",
                c.sample_keys,
            ),
        ]

    return [
        Evidence(id=f"E{index}", metric=metric, value=value, unit=unit, description=desc, keys=keys)
        for index, (metric, value, unit, desc, keys) in enumerate(facts, start=1)
        if value is not None
    ]


def _pct(ratio: float | None) -> float | None:
    return round(ratio * 100, 1) if ratio is not None else None


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None
