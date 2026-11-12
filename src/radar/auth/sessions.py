"""Opaque, server-side sessions. The browser holds a random token; the database holds its hash,
so a database leak does not leak usable sessions, and signing out revokes immediately."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import User, UserSession

COOKIE_NAME = "rr_session"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create(session: AsyncSession, user_id: int, ttl: timedelta) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(token_hash=_hash(token), user_id=user_id, expires_at=datetime.now(UTC) + ttl)
    )
    await session.flush()
    return token


async def resolve(session: AsyncSession, token: str) -> User | None:
    return await session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.token_hash == _hash(token), UserSession.expires_at > datetime.now(UTC))
    )


async def revoke(session: AsyncSession, token: str) -> None:
    await session.execute(delete(UserSession).where(UserSession.token_hash == _hash(token)))
