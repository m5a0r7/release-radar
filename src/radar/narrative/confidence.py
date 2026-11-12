"""Caps model confidence by how much the data can actually support.

LLM self-reported confidence is poorly calibrated; a hypothesis drawn from a handful of items or
from partially synced data should never be presented as near-certain.
"""

from dataclasses import dataclass

from radar.insights.schemas import DriftReport

MAX_CONFIDENCE = 0.9


@dataclass(frozen=True, slots=True)
class ConfidenceCap:
    value: float
    reasons: list[str]


def data_support_cap(report: DriftReport) -> ConfidenceCap:
    cap = MAX_CONFIDENCE
    reasons: list[str] = []

    observed = report.progress.completed_in_period + report.progress.completed_previous_period
    if observed < 10:
        cap = min(cap, 0.5)
        reasons.append(f"Only {observed} items were resolved across the two periods compared.")
    elif observed < 30:
        cap = min(cap, 0.75)
        reasons.append(f"{observed} resolved items is a modest sample.")

    full_weeks = sum(1 for w in report.throughput.weekly if w.full_week)
    if full_weeks < 4:
        cap = min(cap, 0.6)
        reasons.append(f"The period covers only {full_weeks} full weeks.")

    if not report.coverage.complete:
        cap = max(0.3, cap - 0.2)
        reasons.extend(report.coverage.notes)

    return ConfidenceCap(round(cap, 2), reasons)


def calibrate(model_confidence: float, cap: ConfidenceCap) -> float:
    return round(min(model_confidence, cap.value), 2)
