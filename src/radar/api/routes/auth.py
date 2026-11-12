import base64
import binascii
import hmac
import re
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from radar.api.deps import ContainerDep, PrincipalDep, SessionDep
from radar.api.errors import ProblemError
from radar.api.schemas import AuthConfigOut, MeOut, UserOut, WorkspaceOut
from radar.auth import accounts, sessions
from radar.auth.accounts import ExternalIdentity
from radar.config import Settings
from radar.db.models import Identity

router = APIRouter(prefix="/v1", tags=["auth"])

STATE_COOKIE = "rr_oauth_state"
STATE_TTL_SECONDS = 600
# Only same-app paths, never `//host` or a scheme, so `next` cannot become an open redirect.
SAFE_NEXT_RE = re.compile(r"^/(?!/)[A-Za-z0-9/_.\-?=&%]*$")
DEMO = ExternalIdentity(
    provider="demo", subject="demo", login="demo", name="Demo User", email=None, avatar_url=None
)


@router.get("/auth/config", response_model=AuthConfigOut)
async def auth_config(container: ContainerDep) -> AuthConfigOut:
    """Which sign-in methods the server offers."""
    settings = container.settings
    return AuthConfigOut(github=settings.github_login_enabled, demo=settings.auth_dev_login)


@router.get("/auth/github/login", status_code=status.HTTP_302_FOUND)
async def github_login(
    container: ContainerDep, next_path: Annotated[str, Query(alias="next")] = "/"
) -> RedirectResponse:
    if container.github_oauth is None:
        raise ProblemError(404, "GitHub sign-in is not configured")
    next_path = next_path if SAFE_NEXT_RE.fullmatch(next_path) else "/"
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(
        container.github_oauth.authorize_url(state, _callback_url(container.settings)),
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        STATE_COOKIE,
        f"{state}.{_encode(next_path)}",
        max_age=STATE_TTL_SECONDS,
        path="/v1/auth",
        httponly=True,
        samesite="lax",
        secure=container.settings.session_cookie_secure,
    )
    return response


@router.get("/auth/github/callback", status_code=status.HTTP_302_FOUND)
async def github_callback(
    request: Request,
    session: SessionDep,
    container: ContainerDep,
    code: Annotated[str, Query(max_length=512)],
    state: Annotated[str, Query(max_length=128)],
) -> RedirectResponse:
    if container.github_oauth is None:
        raise ProblemError(404, "GitHub sign-in is not configured")
    expected, _, encoded_next = request.cookies.get(STATE_COOKIE, "").partition(".")
    if not expected or not hmac.compare_digest(expected, state):
        raise ProblemError(400, "Sign-in expired", "Start signing in again.")

    profile = await container.github_oauth.profile(code, _callback_url(container.settings))
    user = await accounts.sign_in(
        session,
        ExternalIdentity(
            provider="github",
            subject=profile.id,
            login=profile.login,
            name=profile.name,
            email=profile.email,
            avatar_url=profile.avatar_url,
        ),
    )
    next_path = _decode(encoded_next)
    target = next_path if SAFE_NEXT_RE.fullmatch(next_path) else "/"
    response = RedirectResponse(
        f"{container.settings.app_base_url}{target}", status_code=status.HTTP_302_FOUND
    )
    response.delete_cookie(STATE_COOKIE, path="/v1/auth")
    await _start_session(response, session, container.settings, user.id)
    return response


@router.post("/auth/demo", response_model=MeOut)
async def demo_login(session: SessionDep, container: ContainerDep, response: Response) -> MeOut:
    """Sign in as a shared demo user, for trying the app without an OAuth app."""
    if not container.settings.auth_dev_login:
        raise ProblemError(404, "Demo sign-in is disabled")
    user = await accounts.sign_in(session, DEMO)
    await _start_session(response, session, container.settings, user.id)
    workspace = (await accounts.workspaces_of(session, user.id))[0]
    return MeOut(
        user=UserOut(name=user.name, email=user.email, avatar_url=user.avatar_url, provider="demo"),
        workspace=WorkspaceOut(id=workspace.id, name=workspace.name),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, session: SessionDep, container: ContainerDep, response: Response
) -> None:
    if token := request.cookies.get(sessions.COOKIE_NAME):
        await sessions.revoke(session, token)
    response.delete_cookie(
        sessions.COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=container.settings.session_cookie_secure,
    )


@router.get("/me", response_model=MeOut)
async def me(principal: PrincipalDep, session: SessionDep) -> MeOut:
    provider = await session.scalar(
        select(Identity.provider).where(Identity.user_id == principal.user.id).order_by(Identity.id)
    )
    user = principal.user
    return MeOut(
        user=UserOut(
            name=user.name, email=user.email, avatar_url=user.avatar_url, provider=provider or ""
        ),
        workspace=WorkspaceOut(id=principal.workspace.id, name=principal.workspace.name),
    )


def _encode(path: str) -> str:
    return base64.urlsafe_b64encode(path.encode()).decode().rstrip("=")


def _decode(value: str) -> str:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError):
        return "/"


def _callback_url(settings: Settings) -> str:
    return f"{settings.app_base_url}/v1/auth/github/callback"


async def _start_session(
    response: Response, session: SessionDep, settings: Settings, user_id: int
) -> None:
    ttl = timedelta(hours=settings.session_ttl_hours)
    token = await sessions.create(session, user_id, ttl)
    response.set_cookie(
        sessions.COOKIE_NAME,
        token,
        max_age=int(ttl.total_seconds()),
        path="/",
        httponly=True,
        # Lax keeps the cookie off cross-site POSTs, which is the CSRF defence for this API.
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
