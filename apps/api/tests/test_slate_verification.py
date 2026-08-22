"""The slate cross-check (Batch 64) — the second opinion on "is this fixture on?".

Written against a stub provider rather than a recorded payload, because what is under
test is the *judgement*, not the parsing: which combinations of provider answer mean a
fixture comes off a live card, and — far more important — which ones must leave it alone.

The case that gives the module its shape is :func:`test_postponed_keeps_its_original_date`.
On 2026-08-22 odds-api.io served the whole Scottish Premiership as ``pending`` while the
round was postponed, and a date-only cross-check cleared it: FotMob keeps a postponed
match's original ``utcTime``, so the only thing that gives it away is ``status.cancelled``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.services.football_provider import (
    CompetitionKey,
    FixtureState,
    FootballDataProvider,
    LeagueTable,
    MatchResult,
)
from src.services.odds_provider import Slate, SlateFixture, is_void_status
from src.services.slate_verification import VOID_STATUS, verify_slate

SATURDAY = date(2026, 8, 22)
PREMIERSHIP = ("scotland-premiership", "Scotland - Premiership")


class StubFootball(FootballDataProvider):
    """A football-data source that answers exactly what a test tells it to."""

    def __init__(
        self,
        states: dict[str, list[FixtureState]] | None = None,
        *,
        raises: Exception | None = None,
    ) -> None:
        self._states = states or {}
        self._raises = raises
        self.asked: list[str] = []

    async def close(self) -> None:  # pragma: no cover - nothing to release
        return None

    async def fetch_table(self, competition: CompetitionKey, season: int) -> LeagueTable | None:
        return None

    async def fetch_results(
        self,
        competition: CompetitionKey,
        season: int,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> list[MatchResult]:
        return []

    async def fetch_fixture_states(
        self, competition: CompetitionKey, season: int
    ) -> list[FixtureState]:
        self.asked.append(competition.slug)
        if self._raises is not None:
            raise self._raises
        return self._states.get(competition.slug, [])


def slate_fixture(
    home: str,
    away: str,
    *,
    event_id: str = "1",
    competition: tuple[str, str] = PREMIERSHIP,
    kickoff: datetime | None = None,
) -> SlateFixture:
    return SlateFixture(
        provider_event_id=event_id,
        home=home,
        away=away,
        kickoff_utc=kickoff or datetime(2026, 8, 22, 14, 0, tzinfo=UTC),
        competition=competition[1],
        competition_id=competition[0],
        status="pending",
    )


def state(
    home: str,
    away: str,
    *,
    day: date = SATURDAY,
    cancelled: bool = False,
    reason: str = "",
) -> FixtureState:
    return FixtureState(
        home=home,
        away=away,
        kickoff_utc=datetime(day.year, day.month, day.day, 14, 0, tzinfo=UTC),
        cancelled=cancelled,
        reason=reason,
    )


def one(fixture: SlateFixture) -> Slate:
    return Slate(starts_on=SATURDAY, fixtures=[fixture])


# ── The defect this module exists for ──────────────────────────────────────────


async def test_postponed_keeps_its_original_date():
    """``cancelled`` is the only tell — the date agrees, and the match is still off.

    Rangers v St Mirren, verbatim from the live incident.
    """
    slate = one(slate_fixture("Glasgow Rangers", "St Mirren FC", event_id="72201594"))
    football = StubFootball(
        {
            "scotland-premiership": [
                state("Rangers", "St Mirren", cancelled=True, reason="Postponed")
            ]
        }
    )

    verified, count = await verify_slate(slate, football)

    assert count == 1
    assert verified.fixtures[0].status == VOID_STATUS
    assert is_void_status(verified.fixtures[0].status)


async def test_moved_to_another_date_is_off():
    """The other half: not flagged, simply not listed on the day any more."""
    slate = one(slate_fixture("St. Johnstone FC", "Celtic Glasgow", event_id="72201596"))
    football = StubFootball(
        {"scotland-premiership": [state("St Johnstone", "Celtic", day=date(2026, 9, 15))]}
    )

    verified, count = await verify_slate(slate, football)

    assert count == 1
    assert verified.fixtures[0].status == VOID_STATUS


async def test_healthy_fixture_is_left_alone():
    slate = one(slate_fixture("Motherwell FC", "Aberdeen FC"))
    football = StubFootball({"scotland-premiership": [state("Motherwell", "Aberdeen")]})

    verified, count = await verify_slate(slate, football)

    assert count == 0
    assert verified.fixtures[0].status == "pending"
    assert verified is slate  # unchanged slates are not rebuilt


# ── Failing open: every uncertainty leaves the card as it was ──────────────────


async def test_competition_the_source_does_not_carry_is_left_alone():
    """FotMob has no NI Championship 1 — eight fixtures were unverifiable on the day."""
    fixture = slate_fixture(
        "Ballymena United",
        "Larne FC",
        competition=("northern-ireland-championship-1", "Northern Ireland - Championship 1"),
    )
    football = StubFootball({})

    verified, count = await verify_slate(one(fixture), football)

    assert count == 0
    assert verified.fixtures[0].status == "pending"


async def test_unmatched_names_are_left_alone():
    """No confident pair match is *no opinion*, never a deletion."""
    slate = one(slate_fixture("Some Unknown FC", "Another Unknown FC"))
    football = StubFootball({"scotland-premiership": [state("Rangers", "Celtic")]})

    verified, count = await verify_slate(slate, football)

    assert count == 0
    assert verified.fixtures[0].status == "pending"


async def test_alias_layer_matches_where_a_naive_scorer_would_not():
    """ "RC Warwick" is "Racing Club Warwick". A token scorer rates that 0.33 and deletes it.

    Asserted through the *positive* direction — the pair is matched confidently enough to
    be judged at all — because the danger it guards against is a real fixture being
    removed on a name mismatch.
    """
    slate = one(slate_fixture("RC Warwick", "Coventry Sphinx FC"))
    football = StubFootball(
        {
            "scotland-premiership": [
                state("Racing Club Warwick", "Coventry Sphinx", cancelled=True, reason="Postponed")
            ]
        }
    )

    verified, count = await verify_slate(slate, football)

    assert count == 1, "the alias layer should have matched this pair"


async def test_different_clubs_sharing_a_place_name_do_not_match():
    """Boston United is not Boston Town — and an away side must agree as well."""
    slate = one(slate_fixture("Boston United", "Alfreton Town"))
    football = StubFootball(
        {"scotland-premiership": [state("Boston Town", "Alfreton Town", cancelled=True)]}
    )

    verified, count = await verify_slate(slate, football)

    assert count == 0


async def test_provider_failure_is_left_alone():
    slate = one(slate_fixture("Motherwell FC", "Aberdeen FC"))
    football = StubFootball(raises=RuntimeError("upstream down"))

    verified, count = await verify_slate(slate, football)

    assert count == 0
    assert verified.fixtures[0].status == "pending"


async def test_no_provider_configured_is_left_alone():
    slate = one(slate_fixture("Motherwell FC", "Aberdeen FC"))

    verified, count = await verify_slate(slate, None)

    assert count == 0
    assert verified is slate


# ── Not fooled by a season's other listings ────────────────────────────────────


async def test_reverse_fixture_later_in_the_season_does_not_condemn_todays():
    """Both legs match on names. The date chooses, or every home game reads as moved."""
    slate = one(slate_fixture("Motherwell FC", "Aberdeen FC"))
    football = StubFootball(
        {
            "scotland-premiership": [
                state("Motherwell", "Aberdeen", day=date(2027, 1, 2)),
                state("Motherwell", "Aberdeen"),
            ]
        }
    )

    verified, count = await verify_slate(slate, football)

    assert count == 0
    assert verified.fixtures[0].status == "pending"


async def test_all_listings_on_the_day_cancelled_is_off():
    slate = one(slate_fixture("Motherwell FC", "Aberdeen FC"))
    football = StubFootball(
        {
            "scotland-premiership": [
                state("Motherwell", "Aberdeen", day=date(2027, 1, 2)),
                state("Motherwell", "Aberdeen", cancelled=True, reason="Postponed"),
            ]
        }
    )

    verified, count = await verify_slate(slate, football)

    assert count == 1


# ── Shape of the work ──────────────────────────────────────────────────────────


async def test_one_lookup_per_competition_not_per_fixture():
    slate = Slate(
        starts_on=SATURDAY,
        fixtures=[
            slate_fixture("Motherwell FC", "Aberdeen FC", event_id="1"),
            slate_fixture("Hibernian FC", "Kilmarnock FC", event_id="2"),
            slate_fixture("Falkirk FC", "Heart of Midlothian FC", event_id="3"),
        ],
    )
    football = StubFootball({"scotland-premiership": [state("Motherwell", "Aberdeen")]})

    await verify_slate(slate, football)

    assert football.asked == ["scotland-premiership"]


async def test_only_the_condemned_fixture_is_rewritten():
    slate = Slate(
        starts_on=SATURDAY,
        fixtures=[
            slate_fixture("Motherwell FC", "Aberdeen FC", event_id="1"),
            slate_fixture("Hibernian FC", "Kilmarnock FC", event_id="2"),
        ],
    )
    football = StubFootball(
        {
            "scotland-premiership": [
                state("Motherwell", "Aberdeen"),
                state("Hibernian", "Kilmarnock", cancelled=True, reason="Postponed"),
            ]
        }
    )

    verified, count = await verify_slate(slate, football)

    assert count == 1
    by_id = {f.provider_event_id: f for f in verified.fixtures}
    assert by_id["1"].status == "pending"
    assert by_id["2"].status == VOID_STATUS
    # The shared originals must not have been edited in place — other leagues hold them.
    assert slate.fixtures[1].status == "pending"


@pytest.mark.parametrize("empty", [[], None])
async def test_empty_slate_is_returned_unchanged(empty):
    slate = Slate(starts_on=SATURDAY, fixtures=[])
    football = StubFootball({})

    verified, count = await verify_slate(slate, football)

    assert count == 0
    assert verified is slate
    assert football.asked == []


def test_void_status_is_one_the_rest_of_the_system_acts_on():
    """The whole design rests on this: mark it, and the existing paths do the work."""
    assert is_void_status(VOID_STATUS)
