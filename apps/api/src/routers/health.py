from functools import cache
from pathlib import Path

import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import AsyncSessionLocal

router = APIRouter(prefix="/api/v1/health", tags=["health"])

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@cache
def bundled_migration_head() -> str:
    """The migration head this image carries, read from its own Alembic scripts.

    This is the version signal that survives a CLI shipment. `RAILWAY_GIT_COMMIT_SHA`
    is injected only for GitHub-connected services, so a `railway up` leaves it
    unset and /health reports `sha: unknown` — which is exactly the state the
    2026-08-06 drift went undetected in. The head is intrinsic to the artefact:
    nothing has to be stamped at deploy time for it to be right.

    Cached because the scripts cannot change while the process is running.
    """
    try:
        heads = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()
    except Exception:
        log.warning("could not resolve the bundled migration head")
        return "unknown"
    # Joined rather than [0]: more than one head is itself worth seeing.
    return ",".join(sorted(heads)) if heads else "unknown"


async def _applied_migration(session: AsyncSession) -> str:
    """The revision the database reports, or "unknown".

    Swallows its own failure. Readiness is about whether we can serve traffic,
    and a version probe must never be able to turn a healthy service red. A
    failed statement aborts the surrounding transaction, which is why the caller
    runs this after the readiness query rather than before it.
    """
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        revisions = result.scalars().all()
    except Exception:
        log.warning("could not read the applied migration revision")
        return "unknown"
    return ",".join(sorted(revisions)) if revisions else "unknown"


@router.get("")
async def health() -> dict[str, str]:
    sha = settings.railway_git_commit_sha or "unknown"
    return {"status": "ok", "sha": sha, "migration": bundled_migration_head()}


@router.get("/ready")
async def ready(response: Response) -> dict[str, str]:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            migration = await _applied_migration(session)
    except Exception:
        log.warning("readiness check failed — db unreachable")
        response.status_code = 503
        return {"status": "not_ready", "db": "unreachable"}
    return {"status": "ready", "db": "ok", "migration": migration}
