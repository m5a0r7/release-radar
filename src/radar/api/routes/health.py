from fastapi import APIRouter
from sqlalchemy import text

from radar.api.deps import ContainerDep
from radar.api.errors import ProblemError

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(container: ContainerDep) -> dict[str, str]:
    try:
        async with container.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise ProblemError(503, "Database unavailable") from exc
    return {"status": "ready"}
