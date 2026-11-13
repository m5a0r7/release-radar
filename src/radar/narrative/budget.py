"""Keep the LLM prompt inside a token budget, whatever the size of the release.

Evidence is already aggregated (counts, rates, at most `SAMPLE_KEYS` keys per fact), so prompt
size does not grow with ticket count; only the weekly throughput series grows with the period.
Trimming is deterministic, so the trimmed evidence is a stable cache key.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass

from radar.insights.evidence import Evidence

# Deliberately pessimistic for JSON-heavy text (English prose averages ~4 chars per token).
CHARS_PER_TOKEN = 3
WEEKLY_PREFIX = "throughput.week_"
RECENT_WEEKS = 12
REDUCED_KEYS = 3


@dataclass(frozen=True, slots=True)
class Fitted:
    evidence: list[Evidence]
    notes: list[str]


def estimate_tokens(*texts: str) -> int:
    return sum(len(t) for t in texts) // CHARS_PER_TOKEN + 1


def fit_evidence(
    evidence: list[Evidence], size: Callable[[list[Evidence]], int], budget: int
) -> Fitted | None:
    """Return the richest evidence whose prompt fits `budget` tokens, or None if nothing does."""
    steps: list[tuple[Callable[[list[Evidence]], list[Evidence]], str]] = [
        (lambda ev: ev, ""),
        (
            lambda ev: _limit_keys(ev, REDUCED_KEYS),
            f"Example ticket keys were limited to {REDUCED_KEYS} per fact for the AI.",
        ),
        (
            _recent_weeks,
            f"The AI saw only the last {RECENT_WEEKS} weeks of throughput, plus anomalous weeks.",
        ),
        (lambda ev: _limit_keys(ev, 0), "The AI saw no example ticket keys."),
    ]
    current = evidence
    notes: list[str] = []
    for trim, note in steps:
        current = trim(current)
        if note:
            notes.append(note)
        if size(current) <= budget:
            return Fitted(current, notes)
    return None


def schema_tokens(schema: dict[str, object]) -> int:
    return estimate_tokens(json.dumps(schema))


def _limit_keys(evidence: list[Evidence], limit: int) -> list[Evidence]:
    return [e.model_copy(update={"keys": e.keys[:limit]}) for e in evidence]


def _recent_weeks(evidence: list[Evidence]) -> list[Evidence]:
    weekly = [e for e in evidence if e.metric.startswith(WEEKLY_PREFIX)]
    keep = {e.id for e in weekly[-RECENT_WEEKS:]} | {
        e.id for e in weekly if "anomaly" in e.description
    }
    return [e for e in evidence if not e.metric.startswith(WEEKLY_PREFIX) or e.id in keep]
