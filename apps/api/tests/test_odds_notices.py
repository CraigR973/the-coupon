"""What a pick refused for odds says, in the log and to the site admins. Batch 217.

On 31 Oct every pick in the round was refused with ``ODDS_UNAVAILABLE`` from 03:00 UTC, and
the only trace was a log line that said "rejected the API key" while the provider's body
said Bet365 had gone paid-only. These pin the words without a database; the once-per-round
claim and the inbox rows are driven through the real endpoint in ``test_picks_flow.py``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.models.pick import PickMarket, PickOutcome
from src.routers import picks
from src.services.odds_cache import CachingOddsProvider
from src.services.odds_notices import odds_unavailable_body
from src.services.odds_provider import (
    OddsProviderAPIError,
    OddsProviderBadRequest,
    OddsProviderError,
    OddsProviderKeyRejected,
    OddsProviderRateLimited,
)
from tests.test_odds_cache import PAID_ONLY, _Clock, _CountingProvider, _Log, _paid_only
from tests.test_odds_pricing import _fixture


async def test_the_refused_pick_logs_the_reason_and_tells_the_admins_before_the_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _Log()
    monkeypatch.setattr(picks, "log", recorded)
    inner = _CountingProvider()
    inner.odds_error = _paid_only()
    provider = CachingOddsProvider(inner, ttl_seconds=0.0, clock=_Clock())
    told: list[OddsProviderError] = []

    async def tell_admins(exc: OddsProviderError) -> None:
        told.append(exc)

    with pytest.raises(HTTPException) as refused:
        await picks._snapshot_selection(
            provider,
            _fixture("72203846"),
            PickMarket.MATCH_ODDS,
            PickOutcome.HOME,
            before_upstream=lambda: None,
            on_unavailable=tell_admins,
        )

    assert (refused.value.status_code, refused.value.detail) == (503, "ODDS_UNAVAILABLE")
    [line] = recorded.fields("pick refused: odds unavailable")
    assert line["reason"] == "bookmaker_not_on_plan"
    assert line["provider_said"] == PAID_ONLY
    assert line["fixture"] == "72203846"
    assert [exc.provider_said for exc in told] == [PAID_ONLY]


def test_the_notice_names_the_league_the_bookmaker_and_the_providers_words() -> None:
    assert odds_unavailable_body("2-1 Hibs", _paid_only()) == (
        "2-1 Hibs: a pick was refused because the odds plan does not include Bet365. "
        f'The provider said: "{PAID_ONLY}"'
    )


@pytest.mark.parametrize(
    ("error", "why"),
    [
        (
            OddsProviderKeyRejected("key", provider_said="Invalid API key"),
            'the odds provider rejected the API key. The provider said: "Invalid API key"',
        ),
        (
            OddsProviderRateLimited("odds-api.io /odds rate-limited (429), not retried"),
            "the odds provider's request allowance is used up for now.",
        ),
        (
            OddsProviderBadRequest("odds-api.io /odds unexpected status 400"),
            "the odds provider no longer knows that fixture.",
        ),
        (
            OddsProviderAPIError("odds-api.io /odds failed with status 503 after 3 retries"),
            "the odds provider did not answer.",
        ),
    ],
    ids=["key_rejected", "rate_limited", "fixture_refused", "provider_error"],
)
def test_each_reason_reads_as_its_own_sentence(error: OddsProviderError, why: str) -> None:
    assert odds_unavailable_body("2-1 Hibs", error) == f"2-1 Hibs: a pick was refused because {why}"
