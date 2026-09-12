"""A pick alert has to say *what* has gone, not just that something has. Batch 116.

From the owner's live use of the alerts Batch 107 shipped. ``notify_pick_made``
interpolated ``Pick.runner_name`` raw, and that string is composed from the market alone:
Match Odds gives a team name, a draw gives ``The Draw``, and Both Teams To Score gives the
bare word ``Yes``. So a BTTS claim reached eleven phones as

    Dave picked Yes @ 1.80 · 3/12 picked

— a price, a progress count, and no fixture. **Half the selections the product offers could
not be named in an alert at all**, on the one surface that reaches a phone unprompted, for
a game whose whole shape is a land-grab the rest of the league needs to be able to read.

Driven through the submit endpoint rather than against ``notify_pick_made``, because the
defect was never in that function: it is handed a string, and what was wrong was the string
the caller handed it. A unit test on the notifier would have passed throughout.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response

from src.database import AsyncSessionLocal
from src.models.gameweek_completion import GameweekCompletion
from src.models.league import League
from src.models.pick import PickMarket, PickOutcome
from src.models.profile import Profile
from src.services.betfair import FakeBetfair
from src.services.notification_triggers import _completion_body
from src.services.selection_text import fixture_context, outcome_label, selection_summary
from tests.test_pick_progress_batch_107 import (
    _auth,
    _epl_fixture_id,
    _seeded_round,
    client_and_fake,  # noqa: F401 — imported for its fixture registration
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set — Postgres-backed test"
)

#: The canned card's Premier League tie, which every assertion below names.
HOME, AWAY = "Arsenal", "Chelsea"


async def _claim(
    client: AsyncClient,
    league: League,
    person: Profile,
    fixture_id: str,
    market: str,
    outcome: str,
) -> Response:
    return await client.post(
        f"/api/v1/leagues/{league.slug}/picks",
        json={"fixture_id": fixture_id, "market": market, "outcome": outcome},
        headers=_auth(person),
    )


def _bodies(send: AsyncMock) -> list[str]:
    return [call.args[3] for call in send.await_args_list]


# ── The vocabulary itself ──────────────────────────────────────────────────────


def test_the_api_says_what_the_web_says() -> None:
    """One vocabulary, two implementations, and this is the seam between them.

    They had drifted, not merely diverged in coverage: the API said ``The Draw`` where
    ``lib/coupon.ts`` says ``Draw``, and ``Yes`` where it says ``Both teams score``. A
    member reading a tray entry and a member reading the coupon were reading two names for
    one thing. These five lines are `outcomeLabel`'s five branches, spelled out so a change
    on either side has to change a test on this one.
    """
    label = lambda m, o: outcome_label(m, o, HOME, AWAY)  # noqa: E731
    assert label(PickMarket.MATCH_ODDS, PickOutcome.HOME) == "Arsenal"
    assert label(PickMarket.MATCH_ODDS, PickOutcome.AWAY) == "Chelsea"
    assert label(PickMarket.MATCH_ODDS, PickOutcome.DRAW) == "Draw"
    assert label(PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.YES) == "Both teams score"
    assert label(PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.NO) == "No — not both score"


def test_a_selection_takes_the_context_it_does_not_already_carry() -> None:
    """Batch 105's rule, which is why the alert does not simply append the fixture.

    A Match Odds selection *is* one of the two teams, so what disambiguates it is the other
    one; a draw or a BTTS call names neither, so it takes the pairing. Appending the whole
    fixture would print ``Arsenal (Arsenal v Chelsea)`` — the one word a reader is scanning
    for, twice, pushing the price off the end of a tray line.
    """
    ctx = lambda m, o: fixture_context(m, o, HOME, AWAY)  # noqa: E731
    assert ctx(PickMarket.MATCH_ODDS, PickOutcome.HOME) == "v Chelsea"
    assert ctx(PickMarket.MATCH_ODDS, PickOutcome.AWAY) == "at Arsenal"
    assert ctx(PickMarket.MATCH_ODDS, PickOutcome.DRAW) == "Arsenal v Chelsea"
    assert ctx(PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.YES) == "Arsenal v Chelsea"
    assert ctx(PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.NO) == "Arsenal v Chelsea"


# ── The ordinary pick alert ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_btts_claim_reaches_the_tray_naming_its_fixture(
    client_and_fake: tuple[AsyncClient, FakeBetfair],  # noqa: F811
) -> None:
    """The defect, in the case that had no fixture in it at all."""
    client, fake = client_and_fake
    league, gameweek, people = await _seeded_round(fake, 3)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        claimed = await _claim(client, league, people[0], fixture_id, "BOTH_TEAMS_TO_SCORE", "YES")

    assert claimed.status_code == 201, claimed.text
    body = _bodies(send)[0]
    assert "Both teams score (Arsenal v Chelsea)" in body
    assert "picked Yes @" not in body, "the bare provider word must not reach a phone"
    assert body.endswith("· 1/3 picked")


@pytest.mark.asyncio
async def test_a_draw_claim_reaches_the_tray_naming_its_fixture(
    client_and_fake: tuple[AsyncClient, FakeBetfair],  # noqa: F811
) -> None:
    """The other half of the defect. ``The Draw`` is the provider's word, not the product's."""
    client, fake = client_and_fake
    league, gameweek, people = await _seeded_round(fake, 3)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        claimed = await _claim(client, league, people[0], fixture_id, "MATCH_ODDS", "DRAW")

    assert claimed.status_code == 201, claimed.text
    body = _bodies(send)[0]
    assert "Draw (Arsenal v Chelsea)" in body
    assert "The Draw" not in body


@pytest.mark.asyncio
async def test_a_match_odds_claim_does_not_name_its_own_team_twice(
    client_and_fake: tuple[AsyncClient, FakeBetfair],  # noqa: F811
) -> None:
    """The case that already worked, held to the rule rather than left to chance.

    Naming the fixture unconditionally would have fixed the BTTS line and spoiled this one.
    """
    client, fake = client_and_fake
    league, gameweek, people = await _seeded_round(fake, 3)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        home = await _claim(client, league, people[0], fixture_id, "MATCH_ODDS", "HOME")
        send.reset_mock()
        away = await _claim(client, league, people[1], fixture_id, "MATCH_ODDS", "AWAY")
        away_body = _bodies(send)[0]

    assert (home.status_code, away.status_code) == (201, 201)
    assert "Chelsea (at Arsenal)" in away_body
    assert away_body.count("Chelsea") == 1, "the selection already names one of the two"


# ── The completion alert ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_completion_alert_names_the_fixture_off_the_frozen_row(
    client_and_fake: tuple[AsyncClient, FakeBetfair],  # noqa: F811
) -> None:
    """The harder half: the row is frozen, so the fixture has to be carried onto it.

    Revision ``024`` adds the four values a selection is *named* from rather than a composed
    phrase — the stored value stays a datum, and the next copy revision stays a code change.
    """
    client, fake = client_and_fake
    league, gameweek, people = await _seeded_round(fake, 2)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        await _claim(client, league, people[0], fixture_id, "MATCH_ODDS", "HOME")
        send.reset_mock()
        final = await _claim(client, league, people[1], fixture_id, "BOTH_TEAMS_TO_SCORE", "YES")

    assert final.status_code == 201, final.text
    body = _bodies(send)[0]
    assert body.startswith(f"{people[1].display_name} picked Both teams score (Arsenal v Chelsea)")
    assert body.endswith("· 2/2 picked — all picks are in")

    # The row carries the data, not the sentence.
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                GameweekCompletion.__table__.select().where(
                    GameweekCompletion.gameweek_id == gameweek.id
                )
            )
        ).one()
    assert row.market == PickMarket.BOTH_TEAMS_TO_SCORE.value
    assert row.outcome == PickOutcome.YES.value
    assert (row.fixture_home, row.fixture_away) == (HOME, AWAY)
    assert "(" not in row.selection, "the stored value must stay a datum, not a phrase"


@pytest.mark.asyncio
async def test_the_completion_alert_still_names_the_transition_after_a_pick_moves(
    client_and_fake: tuple[AsyncClient, FakeBetfair],  # noqa: F811
) -> None:
    """The retry case, which is the whole reason the row exists and is frozen.

    A fan-out that failed is picked up by the next submission on the round — by which time
    the member who filled the coupon may have moved their pick. The alert has to describe
    what happened when it filled, fixture included.
    """
    client, fake = client_and_fake
    league, gameweek, people = await _seeded_round(fake, 2)
    fixture_id = await _epl_fixture_id(gameweek)

    with patch(
        "src.services.notification_triggers.send_notification",
        new=AsyncMock(side_effect=RuntimeError("push is down")),
    ):
        await _claim(client, league, people[0], fixture_id, "MATCH_ODDS", "HOME")
        await _claim(client, league, people[1], fixture_id, "BOTH_TEAMS_TO_SCORE", "YES")

    # That member now moves, which rewrites the pick and leaves the completion row alone.
    with patch(
        "src.services.notification_triggers.send_notification", new=AsyncMock(return_value=1)
    ) as send:
        moved = await _claim(client, league, people[1], fixture_id, "BOTH_TEAMS_TO_SCORE", "NO")

    assert moved.status_code in (200, 201), moved.text
    completion = [b for b in _bodies(send) if b.endswith("all picks are in")]
    assert completion, "the undelivered completion must be retried"
    assert "Both teams score (Arsenal v Chelsea)" in completion[0]
    assert "No — not both score" not in completion[0], "the event is the transition, not now"


def test_a_completion_written_before_024_falls_back_to_what_it_has() -> None:
    """No backfill, and nothing honest to backfill from.

    A row written before revision ``024`` has no fixture on it: the round may since have
    settled and the picker may since have moved, so joining back through ``picks`` would
    describe something other than the transition. The fallback is the exact alert that row
    would have produced before this batch, which is the right answer for it.
    """
    legacy = GameweekCompletion(
        gameweek_id=uuid.uuid4(),
        final_picker_name="Dave",
        selection="The Draw",
        odds=Decimal("1.80"),
        member_count=12,
    )
    assert _completion_body(legacy) == (
        "Dave picked The Draw @ 1.80 · 12/12 picked — all picks are in"
    )


def test_the_two_surfaces_render_one_phrase() -> None:
    """``selection_summary`` is the whole of it, and both alerts go through it."""
    assert selection_summary(PickMarket.MATCH_ODDS, PickOutcome.HOME, HOME, AWAY) == (
        "Arsenal (v Chelsea)"
    )
    assert (
        selection_summary(PickMarket.BOTH_TEAMS_TO_SCORE, PickOutcome.NO, HOME, AWAY)
        == "No — not both score (Arsenal v Chelsea)"
    )
