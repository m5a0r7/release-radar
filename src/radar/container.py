from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from radar.config import Settings
from radar.connectors.registry import Connectors
from radar.db.session import create_engine, create_session_factory
from radar.ingest.service import SyncService
from radar.narrative.llm import AnthropicLLM
from radar.narrative.service import NarrativeService


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

    @classmethod
    def build(cls, settings: Settings) -> "Container":
        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        connectors = Connectors(settings)
        llm = AnthropicLLM(settings) if settings.llm_provider == "anthropic" else None
        return cls(
            settings=settings,
            engine=engine,
            sessions=sessions,
            connectors=connectors,
            sync=SyncService(sessions, connectors, settings.github_backfill_days),
            narratives=NarrativeService(llm),
            llm=llm,
        )

    async def aclose(self) -> None:
        if self.llm is not None:
            await self.llm.aclose()
        await self.connectors.aclose()
        await self.engine.dispose()
