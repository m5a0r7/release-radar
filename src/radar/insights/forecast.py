import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

TRIALS = 2000
MAX_WEEKS = 260
SEED = 7


@dataclass(frozen=True, slots=True)
class Forecast:
    remaining: int
    p50_date: date | None
    p85_date: date | None
    on_time_probability: float | None


def monte_carlo_completion(
    remaining: int,
    weekly_throughput: list[int],
    start: date,
    target: date | None,
) -> Forecast:
    """Bootstrap future weeks from observed weekly throughput to estimate a finish date.

    Seeded for reproducibility: the same inputs always produce the same forecast, which keeps
    responses cacheable and the LLM's evidence stable.
    """
    if remaining == 0:
        return Forecast(0, start, start, 1.0 if target is not None else None)
    if not weekly_throughput or not any(weekly_throughput):
        return Forecast(remaining, None, None, 0.0 if target is not None else None)

    rng = random.Random(SEED)  # noqa: S311 - simulation, not security
    weeks_needed: list[float] = []
    for _ in range(TRIALS):
        done, weeks = 0, 0
        while weeks < MAX_WEEKS:
            week = rng.choice(weekly_throughput)
            weeks += 1
            if done + week >= remaining:
                # Interpolate inside the final week so dates are not quantized to whole weeks.
                weeks_needed.append(weeks - 1 + (remaining - done) / week)
                break
            done += week
        else:
            weeks_needed.append(float(MAX_WEEKS))
    weeks_needed.sort()

    def at_percentile(p: float) -> date | None:
        weeks = weeks_needed[min(int(p * TRIALS), TRIALS - 1)]
        return None if weeks >= MAX_WEEKS else start + timedelta(days=math.ceil(weeks * 7))

    on_time = None
    if target is not None:
        allowed_weeks = (target - start).days / 7
        on_time = sum(1 for w in weeks_needed if w <= allowed_weeks) / TRIALS
    return Forecast(remaining, at_percentile(0.5), at_percentile(0.85), on_time)
