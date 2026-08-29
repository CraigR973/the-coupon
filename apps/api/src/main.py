from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.config import docs_urls, settings
from src.database import AsyncSessionLocal
from src.logging_config import configure_logging
from src.middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware
from src.rate_limit import limiter
from src.routers import (
    admin,
    auth,
    coupon,
    football,
    gameweek,
    health,
    league_join_requests,
    league_memberships,
    leagues,
    me,
    notifications,
    picks,
    players,
)
from src.routers.config import router as config_router
from src.scheduler import create_scheduler
from src.services.football_session import football_session
from src.services.odds_session import odds_session
from src.services.rename_notice import send_rename_notices

configure_logging(settings.log_level, settings.secret_values())

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
assert settings.environment is not None


async def _send_pending_rename_notices() -> None:
    """Batch 93's one-off notice, on the one event that means "this batch deployed".

    Never fatal. This is a courtesy message to three people; an unreachable database or a
    push provider having a bad day must not stop the API booting, and the task is
    idempotent, so the next boot simply tries again. See ``services/rename_notice``.
    """
    try:
        async with AsyncSessionLocal() as session:
            sent = await send_rename_notices(session)
            await session.commit()
        if sent:
            log.info("rename notices processed", sent=sent)
    except Exception:
        log.exception("rename notice task failed; continuing startup")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("api starting", environment=settings.environment)
    await _send_pending_rename_notices()
    scheduler = create_scheduler()
    app.state.scheduler = scheduler
    if settings.scheduler_enabled:
        scheduler.start()
        log.info("scheduler started")
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            log.info("scheduler stopped")
        await odds_session.close()
        await football_session.close()


# Docs/OpenAPI are disabled in production (private app — don't expose the schema
# anonymously); kept in dev/staging. (Review finding P3-7.)
_docs = docs_urls(settings.environment)
app = FastAPI(
    title="The Coupon API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=_docs["docs_url"],
    redoc_url=_docs["redoc_url"],
    openapi_url=_docs["openapi_url"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health.router)
app.include_router(config_router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(notifications.router)
app.include_router(leagues.router)
app.include_router(league_memberships.router)
app.include_router(league_join_requests.router)
app.include_router(gameweek.router)
app.include_router(football.router)
app.include_router(picks.router)
app.include_router(coupon.router)
app.include_router(players.router)
app.include_router(admin.router)
