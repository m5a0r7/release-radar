from radar.insights.evidence import Evidence
from radar.narrative.budget import RECENT_WEEKS, estimate_tokens, fit_evidence


def evidence(weeks: int) -> list[Evidence]:
    facts = [
        Evidence(
            id="E1",
            metric="idle.items",
            value=40,
            unit="items",
            description="Idle items",
            keys=[f"K-{i}" for i in range(10)],
        )
    ]
    facts += [
        Evidence(
            id=f"E{i + 2}",
            metric=f"throughput.week_{i:03d}",
            value=i,
            unit="items",
            description="Items resolved" + (" (statistical anomaly)" if i == 1 else ""),
        )
        for i in range(weeks)
    ]
    return facts


def size(ev: list[Evidence]) -> int:
    return estimate_tokens("".join(e.model_dump_json() for e in ev))


def test_small_evidence_is_untouched() -> None:
    full = evidence(4)

    fitted = fit_evidence(full, size, budget=10_000)

    assert fitted is not None and fitted.evidence == full and fitted.notes == []


def test_trimming_keeps_recent_and_anomalous_weeks() -> None:
    full = evidence(53)
    budget = size(full[:1] + full[-RECENT_WEEKS - 1 :])

    fitted = fit_evidence(full, size, budget)

    assert fitted is not None and len(fitted.notes) >= 2
    weeks = [e.metric for e in fitted.evidence if e.metric.startswith("throughput")]
    assert weeks[0] == "throughput.week_001"
    assert weeks[1:] == [f"throughput.week_{i:03d}" for i in range(53 - RECENT_WEEKS, 53)]
    assert fitted.evidence[0].keys == ["K-0", "K-1", "K-2"]


def test_nothing_fits_returns_none() -> None:
    assert fit_evidence(evidence(53), size, budget=10) is None
