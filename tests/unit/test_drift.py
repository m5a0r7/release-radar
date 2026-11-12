from datetime import date, timedelta

from radar.insights.drift import compute_drift
from radar.insights.schemas import DriftStatus
from tests.factories import drift_inputs, item, resolved, scenario


def test_scope_counts_additions_and_removals() -> None:
    scope = compute_drift(scenario()).scope

    assert (scope.at_start, scope.at_end, scope.added, scope.removed) == (6, 6, 1, 1)
    assert scope.added_keys == ["K-B"]
    assert scope.removed_keys == ["K-E"]
    assert scope.change_pct == 0.0


def test_progress_uses_membership_and_resolution_as_of_period_bounds() -> None:
    progress = compute_drift(scenario()).progress

    assert progress.completed_in_period == 2
    assert progress.completed_previous_period == 1
    assert progress.open_at_end == 3
    assert progress.done_at_end == 3
    assert progress.percent_complete == 50.0


def test_items_tagged_at_resolution_count_as_unplanned() -> None:
    planning = compute_drift(scenario()).planning

    assert planning.tagged_at_resolution == 1
    assert planning.unplanned_share == 0.5
    assert planning.sample_keys == ["K-B"]


def test_idle_considers_events_and_linked_code_activity() -> None:
    idle = compute_drift(scenario()).idle

    assert idle.idle_keys == ["K-C"]
    assert idle.idle_share == round(1 / 3, 4)


def test_code_metrics_detect_status_lag_and_unlinked_work() -> None:
    code = compute_drift(scenario()).code

    assert code.linked_merged_in_period == 2
    assert code.unlinked_share == 0.4
    assert code.sample_keys == ["K-G"]


def test_weekly_throughput_and_status() -> None:
    report = compute_drift(scenario())

    assert [w.completed for w in report.throughput.weekly] == [0, 2, 0, 0]
    assert report.throughput.mean_per_full_week == 0.5
    assert report.status is DriftStatus.AT_RISK


def test_spike_week_is_flagged_as_anomaly_but_normal_variation_is_not() -> None:
    start = date(2026, 1, 5)
    per_week = [5, 6, 5, 4, 5, 6, 5, 30]
    items = []
    for week, count in enumerate(per_week):
        day = (start + timedelta(days=7 * week + 2)).isoformat()
        items += [item(f"K-{week}-{n}", "2026-01-01", resolved(day)) for n in range(count)]

    weekly = compute_drift(
        drift_inputs(items, start=start, end=start + timedelta(days=55))
    ).throughput.weekly

    assert [w.anomaly for w in weekly] == [False] * 7 + [True]


def test_empty_release_reports_insufficient_data() -> None:
    report = compute_drift(drift_inputs([]))

    assert report.status is DriftStatus.INSUFFICIENT_DATA
    assert report.planning.unplanned_share is None


def test_burnup_tracks_scope_and_done_week_by_week() -> None:
    report = compute_drift(scenario())

    points = [(p.at.isoformat(), p.scope, p.done) for p in report.burnup]

    assert points[0] == ("2026-03-02", 6, 1)
    assert points[-1] == ("2026-03-29", 6, 3)
    assert len(points) == 1 + len(report.throughput.weekly)


def test_attention_lists_merged_but_open_first_then_idle() -> None:
    report = compute_drift(scenario())

    flagged = [(a.key, a.reason.value, a.days) for a in report.attention.items]

    assert flagged == [("K-G", "merged_not_resolved", 9), ("K-C", "idle", 56)]
    assert report.attention.total == 2
