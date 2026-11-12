import httpx

from radar.config import Settings
from radar.connectors.base import CodeHost, WorkTracker
from radar.connectors.github import GitHubCodeHost
from radar.connectors.http import RetryingFetcher
from radar.connectors.jira import JiraTracker

USER_AGENT = "release-radar/0.1"
SUPPORTED_TRACKERS = frozenset({"jira"})
SUPPORTED_CODE_HOSTS = frozenset({"github"})


class Connectors:
    """Owns one pooled HTTP client per upstream for the process lifetime."""

    def __init__(self, settings: Settings) -> None:
        timeout = httpx.Timeout(settings.http_timeout_seconds, connect=10.0)
        self._jira_client = httpx.AsyncClient(
            base_url=str(settings.jira_base_url),
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        github_headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        if settings.github_token is not None:
            github_headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"
        self._github_client = httpx.AsyncClient(
            base_url=str(settings.github_api_url), timeout=timeout, headers=github_headers
        )
        self._jira = JiraTracker(
            RetryingFetcher(self._jira_client, "jira", settings.http_max_retries),
            page_size=settings.jira_page_size,
            base_url=str(settings.jira_base_url),
        )
        self._github = GitHubCodeHost(
            RetryingFetcher(self._github_client, "github", settings.http_max_retries),
            api_url=str(settings.github_api_url),
        )

    def tracker(self, name: str) -> WorkTracker:
        if name == "jira":
            return self._jira
        raise ValueError(f"unsupported tracker: {name}")

    def code_host(self, name: str) -> CodeHost:
        if name == "github":
            return self._github
        raise ValueError(f"unsupported code host: {name}")

    async def aclose(self) -> None:
        await self._jira_client.aclose()
        await self._github_client.aclose()
