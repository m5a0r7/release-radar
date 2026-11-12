from radar.insights.timeline import is_member, last_activity, membership, resolved_as_of
from tests.factories import RELEASE, added, at, item, removed, reopened, resolved


def test_item_without_release_events_was_in_release_since_creation() -> None:
    intervals = membership(item("K-1", "2026-01-01"), RELEASE)

    assert is_member(intervals, at("2026-01-02"))
    assert not is_member(intervals, at("2025-12-31"))


def test_added_later_then_removed() -> None:
    history = item(
        "K-1", "2026-01-01", added("2026-01-10"), removed("2026-01-20"), in_release=False
    )
    intervals = membership(history, RELEASE)

    assert not is_member(intervals, at("2026-01-05"))
    assert is_member(intervals, at("2026-01-15"))
    assert not is_member(intervals, at("2026-01-25"))


def test_first_event_removal_means_it_started_in_release() -> None:
    history = item("K-1", "2026-01-01", removed("2026-01-10"), in_release=False)

    assert is_member(membership(history, RELEASE), at("2026-01-05"))


def test_events_for_other_releases_are_ignored() -> None:
    history = item("K-1", "2026-01-01", added("2026-01-10", release="999"))

    assert is_member(membership(history, RELEASE), at("2026-01-02"))


def test_resolution_is_reconstructed_through_reopen() -> None:
    history = item(
        "K-1", "2026-01-01", resolved("2026-01-05"), reopened("2026-01-07"), resolved("2026-01-09")
    )

    assert resolved_as_of(history, at("2026-01-04")) is None
    assert resolved_as_of(history, at("2026-01-06")) == at("2026-01-05")
    assert resolved_as_of(history, at("2026-01-08")) is None
    assert resolved_as_of(history, at("2026-01-10")) == at("2026-01-09")


def test_last_activity_ignores_future_events() -> None:
    history = item("K-1", "2026-01-01", added("2026-01-03"), resolved("2026-02-01"))

    assert last_activity(history, at("2026-01-15")) == at("2026-01-03")
