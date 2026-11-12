from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from radar.auth import accounts
from radar.auth.accounts import ExternalIdentity
from radar.config import Settings
from radar.container import Container
from radar.db.models import Project, Workspace
from tests.integration.conftest import GITHUB, JIRA, client_for

GITHUB_WEB = "https://github.test"
VERSIONS = [{"id": "100", "name": "1.0", "released": False}]


@pytest.fixture
def oauth_settings(settings: Settings) -> Settings:
    return Settings.model_validate(
        settings.model_dump()
        | {
            "github_oauth_client_id": "client-id",
            "github_oauth_client_secret": "client-secret",
            "github_oauth_url": GITHUB_WEB,
            "app_base_url": "http://app.test",
        }
    )


@pytest.fixture
async def oauth_client(
    oauth_settings: Settings, container: Container
) -> AsyncIterator[httpx.AsyncClient]:
    oauth_container = Container.build(oauth_settings)
    try:
        async with client_for(oauth_container, oauth_settings) as client:
            yield client
    finally:
        await oauth_container.aclose()


def github_user_api(login: str = "octo", user_id: int = 42) -> Any:
    mock = respx.mock(assert_all_called=False)
    mock.post(f"{GITHUB_WEB}/login/oauth/access_token").respond(
        200, json={"access_token": "gho_token"}
    )
    mock.get(f"{GITHUB}user").respond(
        200, json={"id": user_id, "login": login, "name": "Octo Cat", "avatar_url": None}
    )
    mock.get(f"{JIRA}rest/api/2/project/DEMO/versions").respond(200, json=VERSIONS)
    return mock


async def github_sign_in(client: httpx.AsyncClient, next_path: str = "/") -> httpx.Response:
    login = await client.get("/v1/auth/github/login", params={"next": next_path})
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    return await client.get("/v1/auth/github/callback", params={"code": "c0de", "state": state})


async def test_protected_routes_require_a_session(anonymous: httpx.AsyncClient) -> None:
    for path in ("/v1/projects", "/v1/me", "/v1/jobs/1"):
        response = await anonymous.get(path)
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
    assert (await anonymous.get("/healthz")).status_code == 200


async def test_demo_session_cookie_is_locked_down_and_revocable(
    anonymous: httpx.AsyncClient,
) -> None:
    signed_in = await anonymous.post("/v1/auth/demo")
    cookie = signed_in.headers["set-cookie"].lower()

    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert (await anonymous.get("/v1/me")).json()["user"]["provider"] == "demo"

    token = anonymous.cookies["rr_session"]
    assert (await anonymous.post("/v1/auth/logout")).status_code == 204
    anonymous.cookies.set("rr_session", token)
    assert (await anonymous.get("/v1/me")).status_code == 401


async def test_auth_config_reports_available_methods(
    anonymous: httpx.AsyncClient, oauth_client: httpx.AsyncClient
) -> None:
    assert (await anonymous.get("/v1/auth/config")).json() == {"github": False, "demo": True}
    assert (await oauth_client.get("/v1/auth/config")).json() == {"github": True, "demo": True}


async def test_github_sign_in_creates_account_and_workspace(
    oauth_client: httpx.AsyncClient,
) -> None:
    login = await oauth_client.get("/v1/auth/github/login", params={"next": "/projects"})
    authorize = urlparse(login.headers["location"])
    query = parse_qs(authorize.query)

    assert login.status_code == 302
    assert f"{authorize.scheme}://{authorize.netloc}" == GITHUB_WEB
    assert query["redirect_uri"] == ["http://app.test/v1/auth/github/callback"]
    assert "scope" not in query

    with github_user_api():
        callback = await oauth_client.get(
            "/v1/auth/github/callback", params={"code": "c0de", "state": query["state"][0]}
        )
    me = (await oauth_client.get("/v1/me")).json()

    assert callback.status_code == 302
    assert callback.headers["location"] == "http://app.test/projects"
    assert me["user"] == {
        "name": "Octo Cat",
        "email": None,
        "avatar_url": None,
        "provider": "github",
    }
    assert me["workspace"]["name"] == "Octo's workspace"


async def test_forged_state_is_rejected(oauth_client: httpx.AsyncClient) -> None:
    await oauth_client.get("/v1/auth/github/login")

    response = await oauth_client.get(
        "/v1/auth/github/callback", params={"code": "c0de", "state": "attacker"}
    )

    assert response.status_code == 400
    assert "rr_session" not in oauth_client.cookies


async def test_next_cannot_redirect_off_site(oauth_client: httpx.AsyncClient) -> None:
    with github_user_api():
        callback = await github_sign_in(oauth_client, next_path="//evil.test/phish")

    assert callback.headers["location"] == "http://app.test/"


async def test_workspaces_are_isolated(
    client: httpx.AsyncClient, oauth_client: httpx.AsyncClient
) -> None:
    with github_user_api():
        assert (
            await client.post("/v1/projects", json={"slug": "demo", "tracker_key": "DEMO"})
        ).status_code == 201
        await github_sign_in(oauth_client)
        # The same Jira project can be tracked independently by another workspace.
        assert (
            await oauth_client.post("/v1/projects", json={"slug": "mine", "tracker_key": "DEMO"})
        ).status_code == 201

    assert [p["slug"] for p in (await client.get("/v1/projects")).json()] == ["demo"]
    assert (await client.get("/v1/projects/mine")).status_code == 404
    assert (await client.delete("/v1/projects/mine")).status_code == 404
    assert (await oauth_client.get("/v1/projects/demo")).status_code == 404
    assert (await oauth_client.get("/v1/projects/mine")).status_code == 200


async def test_first_user_adopts_projects_created_before_accounts(session: AsyncSession) -> None:
    legacy = Workspace(name="Imported projects")
    session.add(legacy)
    await session.flush()
    session.add(Project(workspace_id=legacy.id, slug="old", tracker="jira", tracker_key="OLD"))

    first = await accounts.sign_in(
        session, ExternalIdentity("github", "1", "ada", "Ada Lovelace", None, None)
    )
    second = await accounts.sign_in(
        session, ExternalIdentity("github", "2", "alan", "Alan Turing", None, None)
    )

    assert [w.id for w in await accounts.workspaces_of(session, first.id)] == [legacy.id]
    assert legacy.name == "Ada's workspace"
    assert [w.id for w in await accounts.workspaces_of(session, second.id)] != [legacy.id]


def test_demo_login_cannot_be_enabled_in_production() -> None:
    with pytest.raises(ValueError, match="AUTH_DEV_LOGIN"):
        Settings(environment="production", auth_dev_login=True)
