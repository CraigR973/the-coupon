from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.config import docs_urls, settings
from src.logging_config import configure_logging
from src.middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware
from src.rate_limit import limiter
from src.routers import (
    auth,
    coupon,
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
from src.scheduler import create_scheduler
from src.services.odds_session import odds_session

configure_logging(settings.log_level)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)
assert settings.environment is not None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("api starting", environment=settings.environment)
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
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(notifications.router)
app.include_router(leagues.router)
app.include_router(league_memberships.router)
app.include_router(league_join_requests.router)
app.include_router(gameweek.router)
app.include_router(picks.router)
app.include_router(coupon.router)
app.include_router(players.router)
