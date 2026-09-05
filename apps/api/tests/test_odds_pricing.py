"""What the deployment learns about which fixtures a bookmaker prices — Batch 114.

The worked example throughout is the round that prompted the batch: 2-1 Hibs's open round
on 2026-09-05 held **202 fixtures, 103 of them `england-fa-cup`** qualifying ties, and the
sweep log read ``fixtures=202 priced=99``. Bet365 priced not one of the 103. They cost 11
of the 21 requests in every sweep and rendered as rows no member could ever pick, and the
free plan's hourly allowance was gone by 08:06 on a match morning.

These are pure unit tests over unattached ORM rows: the rules are about the marker, not
about the database, and nothing here needs a session.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.models.fixture import Fixture
from src.services.odds_pricing import askable, is_unpriced, pickable, record_observations

NOW = datetime(2026, 9, 5, 8, 6)
RECHECK = 21600.0  # six hours, the shipped default


def _fixture(
    event_id: str,
    *,
    unpriced_since: datetime | None = None,
    checked_at: datetime | None = None,
) -> Fixture:
    fixture = Fixture(
        provider_event_id=event_id,
        home="AFC Portchester",
        away="Sholing",
        kickoff_utc=datetime(2026, 9, 5, 14, 0),
        competition="England - FA Cup",
        competition_id="england-fa-cup",
        odds_unpriced_since_utc=unpriced_since,
        odds_checked_at_utc=checked_at,
    )
    # `id` is server-generated; the filter keys on it, so give it something stable.
    fixture.id = event_id  # type: ignore[assignment]
    return fixture


# ── What a sweep spends a request on ──────────────────────────────────────────


def test_an_unmarked_fixture_is_always_asked_about() -> None:
    """The marker is something the deployment learns; until it has, it asks."""
    fixtures = [_fixture("a"), _fixture("b")]

    assert askable(fixtures, NOW, recheck_seconds=RECHECK) == fixtures


def test_a_marked_fixture_is_left_out_until_its_recheck_falls_due() -> None:
    """The 103, taken out of the hourly bill."""
    fresh = _fixture("just-checked", unpriced_since=NOW, checked_at=NOW)
    due = _fixture(
        "long-ago",
        unpriced_since=NOW - timedelta(days=2),
        checked_at=NOW - timedelta(seconds=RECHECK + 1),
    )

    asked = askable([fresh, due], NOW, recheck_seconds=RECHECK)

    assert asked == [due]


def test_the_production_shape_costs_half_the_sweep_it_used_to() -> None:
    """202 fixtures, 103 of them never priced: 21 requests a sweep becomes 10."""
    priced = [_fixture(f"p{i}") for i in range(99)]
    never = [_fixture(f"u{i}", unpriced_since=NOW, checked_at=NOW) for i in range(103)]

    asked = askable(priced + never, NOW, recheck_seconds=RECHECK)

    assert len(asked) == 99
    assert -(-len(asked) // 10) == 10, "ten requests a sweep, against twenty-one"


def test_a_marker_with_no_check_time_is_asked_about_immediately() -> None:
    """The pair `record_observations` never writes; asking is the safe reading of it."""
    orphan = _fixture("hand-edited", unpriced_since=NOW, checked_at=None)

    assert askable([orphan], NOW, recheck_seconds=RECHECK) == [orphan]


# ── What the card shows ───────────────────────────────────────────────────────


def test_a_marked_fixture_is_kept_off_the_card() -> None:
    """Every one of the 103 rendered as a row no member could ever pick."""
    priced = _fixture("priced")
    never = _fixture("never", unpriced_since=NOW, checked_at=NOW)

    assert pickable([priced, never]) == [priced]


def test_a_round_whose_every_fixture_is_unpriced_still_renders() -> None:
    """An empty card is a worse answer than an honest one."""
    fixtures = [_fixture(f"u{i}", unpriced_since=NOW, checked_at=NOW) for i in range(3)]

    assert pickable(fixtures) == fixtures


def test_an_empty_round_stays_empty() -> None:
    """The floor is for a round that *has* fixtures; it must not invent any."""
    assert pickable([]) == []


def test_a_fixture_somebody_has_claimed_is_never_hidden() -> None:
    """A bookmaker may withdraw a market hours after a member claimed it.

    The price is frozen on the pick and the claim stands, so hiding the fixture would take
    a member's own selection off the screen they made it on and take a rival's claim out of
    the land-grab everyone else is reading.
    """
    claimed = _fixture("claimed", unpriced_since=NOW, checked_at=NOW)
    other = _fixture("other", unpriced_since=NOW, checked_at=NOW)
    priced = _fixture("priced")

    assert pickable([claimed, other, priced], claimed={"claimed"}) == [claimed, priced]


# ── Writing the marker ────────────────────────────────────────────────────────


def test_an_absence_observed_by_a_real_sweep_is_recorded() -> None:
    fixture = _fixture("never")

    changed = record_observations([fixture], observed={"never"}, priced=set(), now=NOW)

    assert changed == 1
    assert is_unpriced(fixture)
    assert fixture.odds_unpriced_since_utc == NOW
    assert fixture.odds_checked_at_utc == NOW


def test_a_fixture_that_turns_priceable_is_unmarked() -> None:
    """A market a bookmaker opens late — a cup tie that draws a Premier League side."""
    fixture = _fixture("late", unpriced_since=NOW - timedelta(days=1), checked_at=NOW)

    changed = record_observations([fixture], observed={"late"}, priced={"late"}, now=NOW)

    assert changed == 1
    assert not is_unpriced(fixture)
    assert fixture.odds_checked_at_utc == NOW


def test_a_priced_fixture_that_is_still_priced_writes_nothing() -> None:
    """The steady state of every sweep — 99 of the 202 — must not touch a row."""
    fixture = _fixture("priced")

    changed = record_observations([fixture], observed={"priced"}, priced={"priced"}, now=NOW)

    assert changed == 0
    assert fixture.odds_checked_at_utc is None


def test_a_still_unpriced_fixture_has_only_its_recheck_moved_on() -> None:
    """Confirming an absence is a re-check, and the bound has to move or it never repeats."""
    first_seen = NOW - timedelta(days=1)
    fixture = _fixture("never", unpriced_since=first_seen, checked_at=first_seen)

    changed = record_observations([fixture], observed={"never"}, priced=set(), now=NOW)

    assert changed == 1
    assert fixture.odds_unpriced_since_utc == first_seen, "since is when we learned it"
    assert fixture.odds_checked_at_utc == NOW


def test_a_fixture_outside_the_evidence_is_left_alone() -> None:
    """A degraded sweep, a cached answer and a withheld browse all arrive as this.

    A provider we cannot reach is not evidence that a fixture has no price, and marking on
    that basis would take a pickable fixture off the card exactly when the source is least
    reliable.
    """
    fixture = _fixture("unknown")

    changed = record_observations([fixture], observed=set(), priced=set(), now=NOW)

    assert changed == 0
    assert not is_unpriced(fixture)
    assert fixture.odds_checked_at_utc is None


def test_a_degraded_sweep_cannot_mark_a_whole_round() -> None:
    """The shape the filter would blank: nothing came back, and nothing may be concluded."""
    fixtures = [_fixture(f"f{i}") for i in range(202)]

    changed = record_observations(fixtures, observed=frozenset(), priced=set(), now=NOW)

    assert changed == 0
    assert pickable(fixtures) == fixtures
