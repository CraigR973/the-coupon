"""Validation envelopes confined to the explicitly addressed new game APIs."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.auth import _bearer, get_current_user
from src.database import AsyncSessionLocal
from src.models.profile import Profile


async def game_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> Profile:
    # Entry services own several short transactions and later quote I/O. The
    # usual request-lifetime auth session must not occupy a second connection.
    async with AsyncSessionLocal() as db:
        player = await get_current_user(credentials, db)
        db.expunge(player)
        await db.commit()
    return player


GameUser = Annotated[Profile, Depends(game_user)]


class GameRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def addressed(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                # Do not echo raw inputs (which may contain credentials), and do
                # not change the legacy routers' established validation responses.
                raise HTTPException(
                    status_code=422,
                    detail={"code": "INVALID_REQUEST", "message": "Check this game's request"},
                ) from exc
            except RateLimitExceeded as exc:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "TOO_MANY_TRIES",
                        "message": "Please wait before reading again",
                        "retry_after_seconds": 60,
                    },
                    headers={"Retry-After": "60"},
                ) from exc
            except StarletteHTTPException as exc:
                if exc.status_code != 400 or isinstance(exc.detail, dict):
                    raise
                # FastAPI turns non-UTF-8 JSON/parser errors into HTTP 400
                # before typed validation. Keep that status in the same envelope.
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_REQUEST", "message": "Check this game's request"},
                ) from exc

        return addressed
