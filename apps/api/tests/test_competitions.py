"""The competitions this deployment plays, asserted as the rules rather than as a list.

Batch 119. The trim is member-visible — the card shrinks, and it is meant to — so what it
removes has to be exactly what the owner decided and nothing else. What is checked here is
the *shape* of a slug, because a hand-listed set of competitions is the failure this batch
exists to stop repeating: ``UK_COMPETITIONS = 30``, ``REQUESTS_PER_SLATE_WALK = 30`` and
``LAUNCH_SATURDAY_FIXTURES = 131`` were all true the day they were written.

The catalogue below is the live one, measured with ``fetch_competitions`` against
odds-api.io on 2026-09-12 — 67 UK competitions — and the pool is the 33 that had ever put
a fixture onto a round in production on the same date. Both are fixed here so the rules can
be asserted against the real vocabulary without a provider request.
"""

from __future__ import annotations

from src.services.competitions import (
    MEASURED_DAILY_WALK,
    MEASURED_PLAYED_CATALOGUE,
    MEASURED_UK_CATALOGUE,
    is_played,
    played,
)

#: Every UK competition odds-api.io carried on 2026-09-12, by slug.
LIVE_CATALOGUE: tuple[str, ...] = (
    "england-championship",
    "england-efl-cup",
    "england-efl-trophy-northern-group-a",
    "england-efl-trophy-northern-group-b",
    "england-efl-trophy-northern-group-c",
    "england-efl-trophy-northern-group-d",
    "england-efl-trophy-northern-group-e",
    "england-efl-trophy-northern-group-f",
    "england-efl-trophy-northern-group-g",
    "england-efl-trophy-northern-group-h",
    "england-efl-trophy-southern-group-a",
    "england-efl-trophy-southern-group-b",
    "england-efl-trophy-southern-group-c",
    "england-efl-trophy-southern-group-d",
    "england-efl-trophy-southern-group-e",
    "england-efl-trophy-southern-group-f",
    "england-efl-trophy-southern-group-g",
    "england-efl-trophy-southern-group-h",
    "england-fa-cup",
    "england-league-one",
    "england-league-two",
    "england-national-league",
    "england-national-league-cup-group-a",
    "england-national-league-cup-group-c",
    "england-premier-league",
    "england-amateur-fa-trophy",
    "england-amateur-isthmian-league-premier-division",
    "england-amateur-league-cup-women-northern",
    "england-amateur-league-cup-women-southern",
    "england-amateur-national-league-north",
    "england-amateur-national-league-south",
    "england-amateur-northern-premier-league-premier-division",
    "england-amateur-southern-league-premier-division-central",
    "england-amateur-southern-league-premier-division-south",
    "england-amateur-super-league-2-women",
    "england-amateur-super-league-women",
    "england-amateur-u21-premier-league-2",
    "england-amateur-u21-premier-league-cup-group-b",
    "england-amateur-u21-premier-league-cup-group-c",
    "england-amateur-u21-premier-league-cup-group-d",
    "england-amateur-u21-premier-league-cup-group-e",
    "england-amateur-u21-premier-league-cup-group-f",
    "england-amateur-u21-premier-league-cup-group-g",
    "england-amateur-u21-premier-league-cup-group-h",
    "england-amateur-u21-premier-league-cup-group-i",
    "england-amateur-u21-premier-league-cup-group-j",
    "england-amateur-u21-premier-league-cup-knockout-stage",
    "england-amateur-u21-professional-development-league",
    "northern-ireland-championship-1",
    "northern-ireland-league-cup",
    "northern-ireland-premiership",
    "northern-ireland-premiership-women-championship-round",
    "northern-ireland-premiership-women-relegation-round",
    "scotland-challenge-cup",
    "scotland-championship",
    "scotland-highland-league",
    "scotland-league-cup",
    "scotland-league-one",
    "scotland-league-two",
    "scotland-premier-league-1-women",
    "scotland-premier-league-2-women",
    "scotland-premier-league-cup-women-knockout-stage",
    "scotland-premiership",
    "wales-cymru-championship-north",
    "wales-cymru-championship-south",
    "wales-cymru-premier",
    "wales-welsh-cup",
)

#: The competitions that had ever carried a fixture onto a round in production, same date.
#: This is the set the *daily* walk is narrowed to, on top of the trim.
LIVE_POOL: tuple[str, ...] = (
    "england-championship",
    "england-efl-cup",
    "england-fa-cup",
    "england-league-one",
    "england-league-two",
    "england-national-league",
    "england-premier-league",
    "england-amateur-fa-trophy",
    "england-amateur-isthmian-league-premier-division",
    "england-amateur-national-league-north",
    "england-amateur-national-league-south",
    "england-amateur-northern-premier-league-premier-division",
    "england-amateur-southern-league-premier-division-central",
    "england-amateur-southern-league-premier-division-south",
    "england-amateur-super-league-2-women",
    "england-amateur-super-league-women",
    "england-amateur-u21-premier-league-2",
    "england-amateur-u21-premier-league-cup-group-g",
    "england-amateur-u21-premier-league-cup-group-j",
    "england-amateur-u21-professional-development-league",
    "northern-ireland-championship-1",
    "northern-ireland-premiership",
    "scotland-championship",
    "scotland-highland-league",
    "scotland-league-cup",
    "scotland-league-cup-group-c",
    "scotland-league-one",
    "scotland-league-two",
    "scotland-premier-league-cup-women-knockout-stage",
    "scotland-premiership",
    "wales-cymru-championship-north",
    "wales-cymru-championship-south",
    "wales-cymru-premier",
)


def test_the_measurements_describe_the_catalogue_they_were_taken_from() -> None:
    """The three recorded numbers, against the vocabulary they were measured on."""
    assert len(LIVE_CATALOGUE) == MEASURED_UK_CATALOGUE
    assert len(played(LIVE_CATALOGUE)) == MEASURED_PLAYED_CATALOGUE
    assert len(played(LIVE_POOL)) == MEASURED_DAILY_WALK


def test_the_trim_removes_thirteen_of_the_thirty_three_the_pool_holds() -> None:
    """The owner's decision, measured against the pool it was taken against.

    Thirteen removed and twenty kept — eleven ``england-amateur-*`` divisions including the
    FA Trophy, and both Northern Ireland divisions. Stated as counts *and* as the removed
    set, because "thirteen" alone would pass for the wrong thirteen.
    """
    dropped = [slug for slug in LIVE_POOL if not is_played(slug)]
    assert len(LIVE_POOL) == 33
    assert len(dropped) == 13
    assert len(played(LIVE_POOL)) == 20
    assert set(dropped) == {
        "england-amateur-fa-trophy",
        "england-amateur-isthmian-league-premier-division",
        "england-amateur-northern-premier-league-premier-division",
        "england-amateur-southern-league-premier-division-central",
        "england-amateur-southern-league-premier-division-south",
        "england-amateur-super-league-2-women",
        "england-amateur-super-league-women",
        "england-amateur-u21-premier-league-2",
        "england-amateur-u21-premier-league-cup-group-g",
        "england-amateur-u21-premier-league-cup-group-j",
        "england-amateur-u21-professional-development-league",
        "northern-ireland-championship-1",
        "northern-ireland-premiership",
    }


def test_the_national_leagues_stay() -> None:
    """The one exception the owner carved out of the amateur rule, both halves of it."""
    assert is_played("england-amateur-national-league-north")
    assert is_played("england-amateur-national-league-south")
    assert is_played("england-amateur-national-league")
    # And the tier above them, which is not filed under the amateur heading at all.
    assert is_played("england-national-league")


def test_the_amateur_exception_is_a_rule_and_not_the_two_slugs_it_matches() -> None:
    """A National League *cup* under the amateur heading is a cup, not a division.

    The difference matters because the provider files cup groups beside divisions and the
    catalogue grows every season. A rule classifies next season's entry the day it appears;
    a list classifies it whenever somebody next re-measures, which on the evidence of this
    batch is not soon enough.
    """
    assert not is_played("england-amateur-national-league-cup-group-a")
    assert not is_played("england-amateur-national-league-trophy")
    assert not is_played("england-amateur-national-leagueish")
    assert not is_played("england-amateur-national-league-east")


def test_ireland_goes_north_and_south() -> None:
    """A deliberate product call, not a side effect of the wording.

    Northern Ireland is a UK division and its two competitions really were on the card.
    The catalogue carries no Republic of Ireland competition today; the rule covers one
    anyway, so the decision survives the provider adding it.
    """
    assert not is_played("northern-ireland-premiership")
    assert not is_played("northern-ireland-championship-1")
    assert not is_played("northern-ireland-league-cup")
    assert not is_played("ireland-premier-division")
    assert not is_played("republic-of-ireland-first-division")


def test_everything_else_is_played() -> None:
    """England, Scotland and Wales keep what they had, cups included."""
    for slug in (
        "england-premier-league",
        "england-championship",
        "england-league-one",
        "england-league-two",
        "england-fa-cup",
        "england-efl-cup",
        "england-efl-trophy-northern-group-a",
        "england-national-league-cup-group-a",
        "scotland-premiership",
        "scotland-highland-league",
        "scotland-league-cup",
        "scotland-premier-league-1-women",
        "wales-cymru-premier",
        "wales-welsh-cup",
    ):
        assert is_played(slug), slug


def test_an_unknown_competition_is_classified_by_the_same_rules() -> None:
    """No release needed for next season's catalogue."""
    assert is_played("scotland-some-new-division-2027")
    assert not is_played("england-amateur-some-new-tier-2027")
    assert not is_played("northern-ireland-some-new-tier-2027")


def test_a_competition_with_no_identity_is_not_played() -> None:
    """Nothing can be drawn from a competition with no slug, and asking would cost a request."""
    assert not is_played("")
    assert not is_played("   ")


def test_matching_is_case_and_whitespace_insensitive() -> None:
    """The value is the provider's, not ours."""
    assert not is_played("  NORTHERN-IRELAND-Premiership  ")
    assert is_played("  England-Premier-League  ")
