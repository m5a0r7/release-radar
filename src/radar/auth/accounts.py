from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import Identity, Membership, User, Workspace

OWNER = "owner"


@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    provider: str
    subject: str
    login: str | None
    name: str
    email: str | None
    avatar_url: str | None


async def sign_in(session: AsyncSession, identity: ExternalIdentity) -> User:
    """Find or create the user behind an external identity. Signing in is signing up."""
    existing = await session.scalar(
        select(User)
        .join(Identity, Identity.user_id == User.id)
        .where(Identity.provider == identity.provider, Identity.subject == identity.subject)
    )
    if existing is not None:
        existing.name = identity.name
        existing.email = identity.email or existing.email
        existing.avatar_url = identity.avatar_url
        return existing

    first_user = not await session.scalar(select(func.count()).select_from(User))
    user = User(name=identity.name, email=identity.email, avatar_url=identity.avatar_url)
    session.add(user)
    await session.flush()
    session.add(
        Identity(
            user_id=user.id,
            provider=identity.provider,
            subject=identity.subject,
            login=identity.login,
        )
    )
    name = f"{identity.name.split()[0]}'s workspace"
    # Projects that predate accounts were migrated into a workspace with no members; the first
    # user adopts it instead of starting empty.
    workspace = await _unowned_workspace(session) if first_user else None
    if workspace is None:
        workspace = Workspace(name=name)
        session.add(workspace)
        await session.flush()
    else:
        workspace.name = name
    session.add(Membership(workspace_id=workspace.id, user_id=user.id, role=OWNER))
    await session.flush()
    return user


async def _unowned_workspace(session: AsyncSession) -> Workspace | None:
    has_members = select(Membership).where(Membership.workspace_id == Workspace.id).exists()
    return await session.scalar(select(Workspace).where(~has_members).order_by(Workspace.id))


async def workspaces_of(session: AsyncSession, user_id: int) -> list[Workspace]:
    return list(
        await session.scalars(
            select(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at, Workspace.id)
        )
    )
