from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from radar.config import Settings


def test_blank_secrets_are_treated_as_unset() -> None:
    settings = Settings(github_token="", anthropic_api_key="  ")

    assert settings.github_token is None
    assert settings.anthropic_api_key is None


def test_secrets_are_not_exposed_in_repr() -> None:
    settings = Settings(github_token="ghp_supersecret")

    assert "ghp_supersecret" not in repr(settings)


def test_hosted_postgres_urls_use_asyncpg() -> None:
    settings = Settings(database_url="postgresql://u:p@db.railway.internal:5432/railway")

    assert settings.database_url == "postgresql+asyncpg://u:p@db.railway.internal:5432/railway"
    assert Settings(database_url="postgres://u@h/d").database_url == "postgresql+asyncpg://u@h/d"


def test_production_demo_needs_an_end_date() -> None:
    with pytest.raises(ValidationError, match="DEMO_UNTIL"):
        Settings(environment="production", auth_dev_login=True)

    settings = Settings(environment="production", auth_dev_login=True, demo_until=date(2026, 12, 1))

    assert settings.demo_login_open(datetime(2026, 12, 1, 23, 59, tzinfo=UTC))
    assert not settings.demo_login_open(datetime(2026, 12, 2, tzinfo=UTC))
