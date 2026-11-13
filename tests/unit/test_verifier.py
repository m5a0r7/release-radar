import pytest

from radar.insights.evidence import Evidence
from radar.narrative.schemas import DraftFinding, DraftRecommendation, NarrativeDraft
from radar.narrative.verifier import verify

EVIDENCE = [
    Evidence(
        id="E1",
        metric="scope.added",
        value=150,
        unit="items",
        description="Added",
        keys=["KAFKA-1"],
    ),
    Evidence(
        id="E2", metric="planning.unplanned_share", value=85.95, unit="%", description="Unplanned"
    ),
    Evidence(
        id="E3",
        metric="forecast.p50_date",
        value="2026-12-16",
        unit="date",
        description="Median date",
    ),
]
KEYS = {"KAFKA-1"}
DATES = ["2026-09-18", "2026-11-12"]


def draft(
    claim: str, ids: list[str], summary: str = "Release 4.5.0 is drifting."
) -> NarrativeDraft:
    return NarrativeDraft(
        summary=summary,
        findings=[DraftFinding(claim=claim, confidence=0.7, evidence_ids=ids)],
    )


def check(d: NarrativeDraft) -> list[str]:
    return verify(d, EVIDENCE, KEYS, DATES, ["4.5.0"])


@pytest.mark.parametrize(
    "claim",
    [
        "150 items were added; 86% of completed work was unplanned.",
        "Roughly 85.9% was unplanned and 150 items were added.",
        "Completion is expected around 2026-12-16, e.g. KAFKA-1.",
    ],
)
def test_grounded_claims_pass(claim: str) -> None:
    assert check(draft(claim, ["E1", "E2", "E3"])) == []


def test_number_not_in_cited_evidence_is_rejected() -> None:
    errors = check(draft("150 items were added.", ["E2"]))

    assert errors == ["finding 1: number 150 does not match the cited evidence"]


def test_invented_number_is_rejected_even_in_summary() -> None:
    errors = check(draft("150 items were added.", ["E1"], summary="Scope grew by 212 items."))

    assert errors == ["summary: number 212 does not match the cited evidence"]


def test_unknown_evidence_id_item_and_date_are_rejected() -> None:
    errors = check(draft("KAFKA-999 slipped to 2027-01-01.", ["E9"]))

    assert "finding 1: unknown evidence ids ['E9']" in errors
    assert "finding 1: unknown item KAFKA-999" in errors
    assert "finding 1: date 2027-01-01 is not in the evidence" in errors


def test_recommendation_items_must_come_from_evidence() -> None:
    d = draft("150 items were added.", ["E1"])
    d.recommendation = DraftRecommendation(
        action="Defer KAFKA-1 and KAFKA-2.",
        rationale="They are idle.",
        item_keys=["KAFKA-1", "KAFKA-2"],
        evidence_ids=["E1"],
    )

    assert check(d) == ["recommendation: unknown item KAFKA-2"]


def test_github_issue_numbers_are_keys_not_numbers() -> None:
    evidence = [*EVIDENCE[:1], EVIDENCE[0].model_copy(update={"id": "E4", "keys": ["#42"]})]
    allowed = {"KAFKA-1", "#42"}

    def run(claim: str) -> list[str]:
        return verify(draft(claim, ["E1"]), evidence, allowed, DATES, ["4.5.0"])

    assert run("150 items were added, including #42.") == []
    assert any("#43" in error for error in run("150 items were added, including #43."))
