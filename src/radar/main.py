from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from radar.api.errors import install_error_handlers
from radar.api.middleware import RequestContextMiddleware
from radar.api.routes import health, insights, projects, syncs
from radar.config import Settings, get_settings
from radar.container import Container
from radar.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = Container.build(settings)
        app.state.container = container
        try:
            yield
        finally:
            await container.aclose()

    app = FastAPI(
        title="Release Radar",
        version="0.1.0",
        summary="Detects release drift across Jira and GitHub and explains it with an LLM.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    for module in (health, projects, syncs, insights):
        app.include_router(module.router)
    return app
