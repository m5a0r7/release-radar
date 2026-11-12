from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (and `.env` in development).

    Upstream base URLs are configuration only and never derived from request input,
    so callers cannot point the service at arbitrary hosts.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://radar:radar@localhost:5432/radar"

    jira_base_url: HttpUrl = HttpUrl("https://issues.apache.org/jira")
    jira_page_size: int = Field(default=100, ge=1, le=500)

    github_api_url: HttpUrl = HttpUrl("https://api.github.com")
    github_token: SecretStr | None = None
    github_backfill_days: int = Field(default=120, ge=1, le=730)

    app_base_url: str = Field(
        default="http://localhost:8080",
        description="Public URL of the web app; sign-in redirects back here.",
    )
    github_oauth_url: HttpUrl = HttpUrl("https://github.com")
    github_oauth_client_id: str | None = None
    github_oauth_client_secret: SecretStr | None = None
    auth_dev_login: bool = Field(
        default=True, description="Offer a no-setup demo sign-in. Never enabled in production."
    )
    session_ttl_hours: int = Field(default=24 * 14, ge=1)
    session_cookie_secure: bool = False

    http_timeout_seconds: float = 60.0
    http_max_retries: int = Field(default=4, ge=0, le=10)

    llm_provider: Literal["anthropic", "template"] = "template"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    llm_max_tokens: int = 2048
    llm_timeout_seconds: float = 90.0

    worker_poll_interval_seconds: float = 2.0
    job_lease_seconds: int = 600
    job_max_attempts: int = 3
    auto_sync_hours: float = Field(
        default=6.0, ge=0, description="Re-sync tracked releases this often; 0 disables."
    )

    max_period_days: int = Field(default=366, ge=7)

    @field_validator(
        "github_token",
        "anthropic_api_key",
        "github_oauth_client_id",
        "github_oauth_client_secret",
        mode="before",
    )
    @classmethod
    def _blank_secret_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("app_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def _production_is_locked_down(self) -> "Settings":
        if self.environment == "production" and self.auth_dev_login:
            raise ValueError("AUTH_DEV_LOGIN must be false in production")
        if (self.github_oauth_client_id is None) != (self.github_oauth_client_secret is None):
            raise ValueError("set both GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET")
        return self

    @property
    def github_login_enabled(self) -> bool:
        return self.github_oauth_client_id is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
