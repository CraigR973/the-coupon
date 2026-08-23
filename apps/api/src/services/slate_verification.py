"""Cross-check a slate against the football-data source before it reaches a card.

**Why this exists.** odds-api.io prices fixtures; it does not reliably know whether one
is still on. On 2026-08-22 it served the entire Scottish Premiership round as ``pending``
while the matches were postponed or already moved to 15 September, and Bet365 was still
quoting prices on them. Two of those — Rangers v St Mirren and St Johnstone v Celtic —
reached members' cards, and one member's pick had to be returned by hand.

That is not a bug in :func:`~src.services.gameweek.sync_slate`. Its void filter is honest
about what it knows: it acts on the odds provider's own word, and the odds provider never
said the word. The missing ingredient is a **second opinion**, which is what this module
adds — FotMob already ships in production for tables and results, needs no key, and did
know.

**Two things make a fixture off, not one.**

1. ``status.cancelled`` is true — the provider's postponement flag; or
2. the fixture is not listed on the slate's date at all.

Checking the date alone is precisely the mistake that let those two games through: FotMob
keeps a postponed match's **original** ``utcTime``, so a postponement and a healthy
fixture look identical on date. Checking ``cancelled`` alone would miss a match quietly
rescheduled to another day. Both, or neither is caught.

**Bookmaker prices are not evidence.** A price says a match is *upcoming*. It says nothing
about whether it is upcoming *today*, and reasoning from live odds to "the fixture is
real" is what delayed the diagnosis on the day.

**Failing open is the whole safety property.** A false positive here deletes a real
fixture off a live card and returns a member's pick — strictly worse than the phantom it
would be preventing, because the member did nothing wrong and may not re-pick in time. So
every uncertainty leaves the fixture exactly as the odds provider gave it:

* the competition is one FotMob does not carry (it has no NI Championship 1, and eight of
  that Saturday's fixtures were unverifiable by any source available);
* neither club name matches confidently — deliberately using
  :mod:`src.services.team_matching`, whose alias layer knows "RC Warwick" is "Racing Club
  Warwick"; a naive token scorer rates that pair 0.33 and would delete a real game;
* the request fails, or the provider is not configured at all.

Only a **confident** match that is confidently off is acted on. Everything else is left
alone and, at worst, settles as ``void`` in the evening sweep the way it always did.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import structlog

from src.services.football_provider import (
    CompetitionKey,
    FixtureState,
    FootballDataProvider,
    season_for,
)
from src.services.odds_provider import UK_TZ, Slate, SlateFixture
from src.services.team_matching import PAIR_THRESHOLD, pair_score

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

#: The status written onto a fixture found to be off. One of
#: :data:`~src.services.odds_provider.VOID_STATUSES`, so every existing path — the link
#: filter in ``sync_slate`` and the pick-returning removal in ``_drop_voided_fixtures`` —
#: acts on it with no further change.
VOID_STATUS = "postponed"


def _uk_date(fixture: FixtureState) -> date:
    """A fixture's kick-off as a UK calendar date, which is what ``starts_on`` is."""
    return fixture.kickoff_utc.astimezone(UK_TZ).date()


def _verdict(
    fixture: SlateFixture, candidates: list[FixtureState], starts_on: date
) -> tuple[bool, str]:
    """Whether ``fixture`` is off, and why. ``(False, "")`` means "leave it alone".

    ``candidates`` are the confident name matches. There can legitimately be more than
    one: a home-and-away pair inside the same season matches both ends just as well, and
    picking the "best" one by name would compare the card against a fixture six months
    away and call today's game moved. So the date does the choosing, not the name score.
    """
    if not candidates:
        return False, ""

    today = [state for state in candidates if _uk_date(state) == starts_on]
    if not today:
        moved_to = min(candidates, key=lambda state: abs(_uk_date(state) - starts_on))
        return True, f"not listed on {starts_on}; nearest is {_uk_date(moved_to)}"

    live = [state for state in today if not state.cancelled]
    if live:
        return False, ""

    # Every listing on the day is flagged off.
    return True, today[0].reason or "cancelled"


async def verify_slate(slate: Slate, football: FootballDataProvider | None) -> tuple[Slate, int]:
    """Return ``slate`` with confirmed-off fixtures marked void, and how many were marked.

    The slate is rebuilt rather than mutated — :class:`SlateFixture` instances are shared
    between the leagues that play the same window, so editing one in place would edit it
    for every caller of the same fetch.

    One pass per competition on the card, each served from the adapter's memoised league
    payload, so the cost is the number of *distinct competitions* and not the number of
    fixtures. Called once per shared fetch in
    :func:`~src.services.gameweek.discover_fixtures`, which means two leagues on the same
    window share this verification exactly as they share the fetch behind it.
    """
    if football is None or not slate.fixtures:
        return slate, 0

    by_competition: dict[tuple[str, str], list[SlateFixture]] = defaultdict(list)
    for fixture in slate.fixtures:
        by_competition[(fixture.competition_id, fixture.competition)].append(fixture)

    season = season_for(slate.starts_on)
    voided: dict[str, str] = {}
    unverifiable = 0

    for (slug, name), fixtures in by_competition.items():
        competition = CompetitionKey(slug=slug, name=name)
        try:
            states = await football.fetch_fixture_states(competition, season)
        except Exception:
            # A source that cannot answer is a source with no opinion. Never a reason to
            # touch a card — least of all on the refresh that runs closest to the lock.
            log.warning("slate verification unavailable", competition=name, exc_info=True)
            unverifiable += len(fixtures)
            continue

        if not states:
            log.info("slate verification: competition not carried", competition=name)
            unverifiable += len(fixtures)
            continue

        for fixture in fixtures:
            scored = [
                state
                for state in states
                if pair_score(fixture.home, fixture.away, state.home, state.away) >= PAIR_THRESHOLD
            ]
            if not scored:
                unverifiable += 1
                continue
            off, why = _verdict(fixture, scored, slate.starts_on)
            if off:
                voided[fixture.provider_event_id] = why

    if voided:
        log.warning(
            "slate verification found called-off fixtures",
            starts_on=str(slate.starts_on),
            voided=len(voided),
            unverifiable=unverifiable,
            fixtures=[
                f"{f.home} v {f.away} ({voided[f.provider_event_id]})"
                for f in slate.fixtures
                if f.provider_event_id in voided
            ],
        )
    else:
        log.info(
            "slate verified",
            starts_on=str(slate.starts_on),
            checked=len(slate.fixtures),
            unverifiable=unverifiable,
        )

    if not voided:
        return slate, 0

    return (
        Slate(
            starts_on=slate.starts_on,
            fixtures=[
                fixture.model_copy(update={"status": VOID_STATUS})
                if fixture.provider_event_id in voided
                else fixture
                for fixture in slate.fixtures
            ],
        ),
        len(voided),
    )
