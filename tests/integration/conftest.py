import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from radar.config import Settings, get_settings
from radar.container import Container
from radar.db.models import Base
from radar.jobs.worker import Worker
from radar.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://radar:radar@localhost:5432/radar_test"
)
JIRA = "https://jira.test/jira/"
GITHUB = "https://api.github.test/"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,
        jira_base_url=JIRA,
        github_api_url=GITHUB,
        github_backfill_days=730,
        http_max_retries=0,
        llm_provider="template",
    )


@pytest.fixture(scope="session")
async def migrated(settings: Settings) -> None:
    """Build the schema with the real migrations, so they are tested too."""
    os.environ["DATABASE_URL"] = settings.database_url
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")


@pytest.fixture
async def container(settings: Settings, migrated: None) -> AsyncIterator[Container]:
    container = Container.build(settings)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with container.engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield container
    await container.aclose()


@pytest.fixture
async def session(container: Container) -> AsyncIterator[AsyncSession]:
    async with container.sessions() as session:
        yield session


@pytest.fixture
async def client(container: Container, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    app.state.container = container
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def worker(container: Container, settings: Settings) -> Worker:
    return Worker(container.sessions, container.sync, settings)
