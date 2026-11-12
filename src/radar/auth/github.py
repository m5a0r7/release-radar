"""GitHub OAuth (authorization code flow). No scopes are requested: sign-in only needs the
public profile, and the access token is discarded after reading it."""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from radar.config import Settings
from radar.connectors.errors import UpstreamError


@dataclass(frozen=True, slots=True)
class GitHubProfile:
    id: str
    login: str
    name: str
    email: str | None
    avatar_url: str | None


class GitHubOAuth:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        if settings.github_oauth_client_id is None or settings.github_oauth_client_secret is None:
            raise ValueError("GitHub OAuth is not configured")
        self._client_id = settings.github_oauth_client_id
        self._client_secret = settings.github_oauth_client_secret.get_secret_value()
        self._oauth_url = str(settings.github_oauth_url).rstrip("/")
        self._api_url = str(settings.github_api_url).rstrip("/")
        self._client = client

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "allow_signup": "true",
            }
        )
        return f"{self._oauth_url}/login/oauth/authorize?{query}"

    async def profile(self, code: str, redirect_uri: str) -> GitHubProfile:
        token_response = await self._client.post(
            f"{self._oauth_url}/login/oauth/access_token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token = token_response.json().get("access_token") if token_response.is_success else None
        if not token:
            raise UpstreamError("github", "the sign-in code was rejected")

        user_response = await self._client.get(
            f"{self._api_url}/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if not user_response.is_success:
            raise UpstreamError("github", "could not read the user profile")
        raw = user_response.json()
        return GitHubProfile(
            id=str(raw["id"]),
            login=raw["login"],
            name=raw.get("name") or raw["login"],
            email=raw.get("email"),
            avatar_url=raw.get("avatar_url"),
        )
