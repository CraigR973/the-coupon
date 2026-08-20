"""What this deployment can actually do — the features the client must not guess at.

One endpoint, and it exists for one reason. Profile-picture upload is provisioned per
environment (``AVATAR_STORAGE`` plus a bucket, see ``docs/runbooks/avatar-storage.md``),
so whether it works is a property of the *deployment*, not of the member or the build.
The web app had no way to know, and Batch 42's judgement was that a visible control that
always fails is worse for a member than no control at all — which left the upload control
built and unmounted for a whole batch.

Deliberately *not* on ``PlayerInfo``, where it would have been one line: the client
stores that at login and only refreshes it on the next one, so a member signed in before
the bucket was provisioned would carry a stale ``false`` until they logged out. A
capability that changes when an environment variable changes has to be read, not
remembered.

Authenticated, because nothing unauthenticated needs it, and it says a little about how
the deployment is configured.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.auth import CurrentUser
from src.services.avatar_storage import AvatarStorage, avatar_storage

router = APIRouter(prefix="/api/v1/config", tags=["config"])


class ClientConfig(BaseModel):
    """Feature availability, as this deployment is configured right now."""

    #: True when ``POST /auth/me/avatar`` has somewhere to put the bytes. False means it
    #: answers 503, and the web app leaves its upload control unmounted.
    avatar_uploads: bool


@router.get("", response_model=ClientConfig)
async def client_config(
    user: CurrentUser,  # noqa: ARG001 — authentication is the point, the identity is not
    storage: Annotated[AvatarStorage, Depends(avatar_storage)],
) -> ClientConfig:
    """What the client may offer. Read on demand, never cached across a config change."""
    return ClientConfig(avatar_uploads=storage.enabled)
