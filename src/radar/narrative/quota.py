"""Per-workspace LLM quotas, backed by the `llm_calls` ledger.

Each call is reserved before it is made, under a transaction-scoped advisory lock on the
workspace, so concurrent requests cannot both pass a nearly exhausted quota. Pending calls count
towards the request limit immediately and towards the token limit once they complete.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radar.db.models import LlmCall

LOCK_NAMESPACE = 0x4C4C4D  # "LLM"; keeps these locks apart from other advisory locks
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class LlmLimits:
    requests_per_hour: int
    tokens_per_day: int


class QuotaExceededError(Exception):
    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class UsageLedger:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], limits: LlmLimits) -> None:
        self._sessions = sessions
        self._limits = limits

    async def reserve(self, workspace_id: int, release_id: int | None, model: str) -> int:
        """Record a pending call, or raise `QuotaExceededError`."""
        async with self._sessions() as session, session.begin():
            await session.execute(select(func.pg_advisory_xact_lock(LOCK_NAMESPACE, workspace_id)))
            now = datetime.now(UTC)
            in_workspace = LlmCall.workspace_id == workspace_id

            hourly, oldest_hourly = (
                await session.execute(
                    select(func.count(), func.min(LlmCall.created_at)).where(
                        in_workspace, LlmCall.created_at > now - HOUR
                    )
                )
            ).one()
            if hourly >= self._limits.requests_per_hour:
                raise QuotaExceededError(
                    f"This workspace reached {self._limits.requests_per_hour} AI explanations "
                    "per hour.",
                    _seconds_until(oldest_hourly + HOUR, now),
                )

            daily, oldest_daily = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(LlmCall.input_tokens + LlmCall.output_tokens), 0),
                        func.min(LlmCall.created_at),
                    ).where(in_workspace, LlmCall.created_at > now - DAY)
                )
            ).one()
            if daily >= self._limits.tokens_per_day:
                raise QuotaExceededError(
                    f"This workspace used its daily AI budget of {self._limits.tokens_per_day} "
                    "tokens.",
                    _seconds_until(oldest_daily + DAY, now),
                )

            call = LlmCall(
                workspace_id=workspace_id, release_id=release_id, model=model, outcome="pending"
            )
            session.add(call)
            await session.flush()
            return call.id

    async def complete(
        self, call_id: int, outcome: str, input_tokens: int, output_tokens: int
    ) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(LlmCall)
                .where(LlmCall.id == call_id)
                .values(outcome=outcome, input_tokens=input_tokens, output_tokens=output_tokens)
            )


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, math.ceil((moment - now).total_seconds()))
