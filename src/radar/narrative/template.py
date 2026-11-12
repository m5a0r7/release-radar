"""Deterministic narrator: used when no LLM is configured, and as the fallback when it fails.

It only restates evidence (no hypotheses), so it always passes verification.
"""

from radar.insights.evidence import Evidence
from radar.insights.schemas import DriftReport
from radar.narrative.schemas import DraftFinding, DraftRecommendation, NarrativeDraft

TEMPLATE_CONFIDENCE = 0.9


def template_draft(report: DriftReport, evidence: list[Evidence]) -> NarrativeDraft:
    ids = {e.metric: e.id for e in evidence}
    values = {e.metric: e.value for e in evidence}
    findings: list[DraftFinding] = []

    def add(claim: str, *metrics: str) -> None:
        if all(m in ids for m in metrics):
            findings.append(
                DraftFinding(
                    claim=claim,
                    confidence=TEMPLATE_CONFIDENCE,
                    evidence_ids=[ids[m] for m in metrics],
                )
            )

    add(
        f"Scope moved from {values.get('scope.at_start')} to {values.get('scope.at_end')} items "
        f"({values.get('scope.added')} added, {values.get('scope.removed')} removed).",
        "scope.at_start",
        "scope.at_end",
        "scope.added",
        "scope.removed",
    )
    add(
        f"{values.get('progress.completed')} items were resolved, versus "
        f"{values.get('progress.completed_previous')} in the previous period.",
        "progress.completed",
        "progress.completed_previous",
    )
    add(
        f"{values.get('planning.unplanned_share')}% of completed items were only added to the "
        "release when they were resolved.",
        "planning.unplanned_share",
    )
    add(
        f"{values.get('idle.items')} open items have had no activity for "
        f"{values.get('idle.threshold_days')}+ days.",
        "idle.items",
        "idle.threshold_days",
    )
    if "forecast.p50_date" in ids:
        add(
            f"At the current pace the remaining {values.get('forecast.remaining')} items finish "
            f"around {values.get('forecast.p50_date')}.",
            "forecast.remaining",
            "forecast.p50_date",
        )

    recommendation = None
    if report.idle.idle_keys and "idle.items" in ids:
        recommendation = DraftRecommendation(
            action="Review the idle items and move those nobody is working on to a later release.",
            rationale="Idle items inflate the remaining scope and make the forecast look worse.",
            item_keys=report.idle.idle_keys,
            evidence_ids=[ids["idle.items"]],
        )

    status = report.status.value.replace("_", " ")
    return NarrativeDraft(
        summary=f"Release {report.release.name} is {status} for the selected period.",
        findings=findings
        or [
            DraftFinding(
                claim="No release activity was recorded in the period.",
                confidence=TEMPLATE_CONFIDENCE,
                evidence_ids=[evidence[0].id],
            )
        ],
        recommendation=recommendation,
    )
