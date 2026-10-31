"""Telling the site admins that picks are being refused for want of odds. Batch 217.

On 31 Oct the round opened at 03:00 UTC and refused every pick with ``ODDS_UNAVAILABLE``
(16 by 10:30) while the card showed cached prices, and nothing told anybody: the reason
sat in a log line that blamed the key. This sends it to the people who can act on it,
from the refused request itself, so it arrives within seconds of the first refusal.

**Once per round per reason.** The claim is Batch 213's ``notification_sends`` row — kind
``odds_unavailable``, subject ``<round id>:<reason>`` — inserted under its unique
constraint in the same transaction as the inbox rows. Concurrent refusals and redeploys
race on that insert and only one of them sends; every later refusal costs one insert that
finds the claim taken. Another reason in the same round is news and is sent, and so is
the same reason in another round.

The inbox row hangs on the round's league and links to the admin dashboard. There is no
mute toggle of its own, like the backup and discovery alarms, so global mute, a muted
league and quiet hours are what hold it back.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.notification_triggers import PreparedFanout, _admin_players
from src.services.odds_provider import (
    OddsFailure,
    OddsProviderBookmakerNotOnPlan,
    OddsProviderError,
    odds_failure,
)
from src.services.payment_notices import _claim
from src.services.push_notification_service import (
    collect_notification_intents,
    prepare_collected_notifications,
    send_notification,
)

ODDS_UNAVAILABLE = "odds_unavailable"

_TITLE = "A pick was refused: no odds"

#: Why, in the words the notice uses. The provider's own words follow when it gave any.
_WHY: dict[OddsFailure, str] = {
    OddsFailure.BOOKMAKER_NOT_ON_PLAN: "the odds plan does not include the bookmaker",
    OddsFailure.KEY_REJECTED: "the odds provider rejected the API key",
    OddsFailure.RATE_LIMITED: "the odds provider's request allowance is used up for now",
    OddsFailure.FIXTURE_REFUSED: "the odds provider no longer knows that fixture",
    OddsFailure.PROVIDER_ERROR: "the odds provider did not answer",
}


def odds_unavailable_body(league_name: str, exc: OddsProviderError) -> str:
    """Which league, why, and what the provider said."""
    why = _WHY[odds_failure(exc)]
    if isinstance(exc, OddsProviderBookmakerNotOnPlan) and exc.bookmaker:
        why = f"the odds plan does not include {exc.bookmaker}"
    said = f' The provider said: "{exc.provider_said}"' if exc.provider_said else ""
    return f"{league_name}: a pick was refused because {why}.{said}"


async def prepare_odds_unavailable_notice(
    session: AsyncSession,
    *,
    league_id: uuid.UUID,
    league_name: str,
    gameweek_id: uuid.UUID,
    exc: OddsProviderError,
    now: datetime,
) -> PreparedFanout | None:
    """Claim this round's notice for this reason, write its inbox rows and copy its pushes.

    ``None`` when the claim was already taken: the admins have been told this reason for
    this round. The caller commits, and only then delivers the returned pushes.
    """
    subject = f"{gameweek_id}:{odds_failure(exc).value}"
    if not await _claim(session, ODDS_UNAVAILABLE, subject, now):
        return None
    body = odds_unavailable_body(league_name, exc)
    admins = await _admin_players(session)
    with collect_notification_intents() as intents:
        for admin in admins:
            await send_notification(
                session,
                admin.id,
                _TITLE,
                body,
                data={"type": ODDS_UNAVAILABLE, "league_id": str(league_id), "url": "/admin"},
                tag=f"odds-unavailable-{gameweek_id}",
                timezone_name=admin.timezone,
                now_utc=now,
                league_id=league_id,
            )
    notifications = await prepare_collected_notifications(session, intents)
    return PreparedFanout(notifications=tuple(notifications), targeted=len(admins))
