from dataclasses import dataclass

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from radar.auth.github import GitHubOAuth
from radar.config import Settings
from radar.connectors.registry import Connectors
from radar.db.session import create_engine, create_session_factory
from radar.ingest.service import SyncService
from radar.narrative.llm import AnthropicLLM
from radar.narrative.quota import LlmLimits, UsageLedger
from radar.narrative.service import NarrativeLimits, NarrativeService

log = structlog.get_logger(__name__)


@dataclass
class Container:
    """Process-wide dependencies, built once at startup and closed at shutdown."""

    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    connectors: Connectors
    sync: SyncService
    narratives: NarrativeService
    llm: AnthropicLLM | None
    oauth_client: httpx.AsyncClient
    github_oauth: GitHubOAuth | None

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        connectors = Connectors(settings)
        llm = AnthropicLLM(settings) if settings.llm_provider == "anthropic" else None
        log.info(
            "llm_config",
            provider=settings.llm_provider,
            model=settings.anthropic_model if llm is not None else "template",
        )
        oauth_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        github_oauth = (
            GitHubOAuth(settings, oauth_client) if settings.github_login_enabled else None
        )
        return cls(
            settings=settings,
            engine=engine,
            sessions=sessions,
            connectors=connectors,
            sync=SyncService(
                sessions, connectors, settings.github_backfill_days, settings.sync_max_work_items
            ),
            narratives=NarrativeService(
                llm,
                ledger=UsageLedger(
                    sessions,
                    LlmLimits(settings.llm_requests_per_hour, settings.llm_tokens_per_day),
                ),
                limits=NarrativeLimits(
                    max_input_tokens=settings.llm_max_input_tokens,
                    max_output_tokens=settings.llm_max_tokens,
                    max_concurrency=settings.llm_max_concurrency,
                ),
            ),
            llm=llm,
            oauth_client=oauth_client,
            github_oauth=github_oauth,
        )

    async def aclose(self) -> None:
        if self.llm is not None:
            await self.llm.aclose()
        await self.oauth_client.aclose()
        await self.connectors.aclose()
        await self.engine.dispose()
