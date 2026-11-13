"""Grounding checks: the narrative may only state numbers, dates and items found in evidence."""

import re
from collections.abc import Iterable

from radar.insights.evidence import Evidence
from radar.narrative.schemas import NarrativeDraft

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Jira keys (KAFKA-123) and GitHub issue numbers (#123).
ITEM_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9_]+-\d+\b|(?<![\w/&#])#\d+\b")
VERSION_RE = re.compile(r"\b\d+(?:\.\d+){2,}\b")
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)")


def verify(
    draft: NarrativeDraft,
    evidence: list[Evidence],
    allowed_keys: set[str],
    context_dates: Iterable[str],
    context_terms: Iterable[str] = (),
) -> list[str]:
    """Return human-readable grounding errors; an empty list means the draft is grounded.

    `context_terms` (e.g. the release name "4.5") are removed before numbers are checked.
    """
    terms = [t for t in context_terms if t]
    by_id = {e.id: e for e in evidence}
    all_numbers = _numeric_values(evidence)
    known_dates = set(context_dates) | {
        d for e in evidence for d in DATE_RE.findall(f"{e.value} {e.description}")
    }
    errors: list[str] = []

    def check_text(label: str, text: str, numbers: list[float]) -> None:
        for key in ITEM_KEY_RE.findall(text):
            if key not in allowed_keys:
                errors.append(f"{label}: unknown item {key}")
        for day in DATE_RE.findall(text):
            if day not in known_dates:
                errors.append(f"{label}: date {day} is not in the evidence")
        for term in terms:
            text = text.replace(term, " ")
        for raw in _numbers_in(text):
            if not any(_matches(raw, value) for value in numbers):
                errors.append(f"{label}: number {raw} does not match the cited evidence")

    def cited(label: str, ids: list[str]) -> list[float]:
        missing = [i for i in ids if i not in by_id]
        if missing:
            errors.append(f"{label}: unknown evidence ids {missing}")
        return _numeric_values(by_id[i] for i in ids if i in by_id)

    check_text("summary", draft.summary, all_numbers)
    for index, finding in enumerate(draft.findings, start=1):
        label = f"finding {index}"
        numbers = cited(label, finding.evidence_ids)
        check_text(label, finding.claim, numbers)
        if finding.hypothesis:
            check_text(f"{label} hypothesis", finding.hypothesis, numbers)

    if (rec := draft.recommendation) is not None:
        numbers = cited("recommendation", rec.evidence_ids)
        check_text("recommendation", f"{rec.action} {rec.rationale}", numbers)
        for key in rec.item_keys:
            if key not in allowed_keys:
                errors.append(f"recommendation: unknown item {key}")
    return list(dict.fromkeys(errors))


def _numbers_in(text: str) -> list[str]:
    stripped = VERSION_RE.sub(" ", ITEM_KEY_RE.sub(" ", DATE_RE.sub(" ", text)))
    return NUMBER_RE.findall(stripped)


def _numeric_values(evidence: Iterable[Evidence]) -> list[float]:
    return [float(e.value) for e in evidence if isinstance(e.value, int | float)]


def _matches(raw: str, value: float) -> bool:
    """Accept the evidence value written at any rounding precision (38.46 -> 38.5 or 38)."""
    written = float(raw)
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return abs(written - value) <= 0.5 * 10.0**-decimals + 1e-9
