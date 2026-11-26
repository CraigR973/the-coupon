"""Which competitions this deployment plays, as rules over the provider's own slugs.

Batch 119, from the week 2-1 Hibs had nothing to play. Fixture discovery costs **one
request per competition per (window, date)**, the catalogue measured live on 2026-09-12
holds **67** UK competitions, and the free plan allows 100 requests an hour. Two windows
across a two-week horizon is ``2 x 2 x 67 = 268`` requests: the daily run took a ``429``
partway through and produced nothing, every day, for a week.

Two independent narrowings bring that inside the plan, and they are kept apart on
purpose because only one of them is a product decision:

* **the trim, here** — the deployment stops *playing* competitions nobody wants to pick.
  It is member-visible: the card shrinks, and it is meant to. Measured against the
  fixture pool on 2026-09-27, of the 36 competitions that have ever carried a fixture
  onto a round this removes **13** and keeps **23**.
* **the never-used skip** (:func:`~src.services.gameweek.pooled_competition_ids`) — the
  daily run stops walking competitions that have never once put a fixture on a round.
  That one is invisible: those competitions return nothing whether they are asked or not,
  and a weekly full-catalogue walk is what stops the skip becoming a ratchet.

**Rules, not a list.** The trim is expressed as three predicates over the slug because a
hand-listed set is exactly the failure this batch exists to stop repeating —
``UK_COMPETITIONS = 30`` and ``LAUNCH_SATURDAY_FIXTURES = 131`` were both true when they
were written. A competition the provider adds next season is classified by the same rules
the day it appears, with no release.

**The trim does not touch a round that already exists.** ``sync_slate`` only ever adds
links, so a round discovered before this shipped keeps the fixtures it holds — which is
what it must do, because members may already have picks on them. Rounds discovered from
here on are drawn from the kept set.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: Ireland, north and south. In practice this is Northern Ireland — the catalogue carries
#: no Republic of Ireland competition at all — and **Northern Ireland is a UK division**,
#: so dropping it is a deliberate product call (owner decision, 2026-09-11) rather than a
#: side effect of the word "Ireland". The other prefixes are here so the rule survives the
#: provider carrying an Irish league it does not carry today.
_IRISH_PREFIXES: tuple[str, ...] = (
    "ireland-",
    "northern-ireland-",
    "republic-of-ireland-",
)

#: The provider files the whole non-league English pyramid under ``england-amateur-``,
#: alongside the women's and U21 competitions. All of it goes except the National League
#: divisions, which are the tier immediately below the EFL and the one a member recognises.
_ENGLAND_AMATEUR_PREFIX = "england-amateur-"

#: What survives :data:`_ENGLAND_AMATEUR_PREFIX`: the National League and its two regional
#: divisions, and nothing that merely begins with their name. Written as a pattern rather
#: than as the two slugs that match it today so an ``england-amateur-national-league-cup-*``
#: group — a cup, not a division — is dropped by the same rule that keeps North and South.
_NATIONAL_LEAGUE_DIVISION = re.compile(r"^national-league(-north|-south)?$")


#: What the provider carries and what this deployment plays of it: **measured live with
#: ``fetch_competitions`` on 2026-09-12**, 67 UK competitions are in the catalogue and 41
#: are played after the trim; **remeasured from the production fixture pool on
#: 2026-09-27**, 23 of those have ever put a fixture in the pool and so are what a daily
#: walk actually costs.
#:
#: Measurements with a date against them, not design constants. That distinction is the
#: whole of Batch 119: ``UK_COMPETITIONS = 30`` in the budget suite and
#: ``REQUESTS_PER_SLATE_WALK = 30`` in ``admin_ops`` were both real measurements of a
#: catalogue that had since grown to 67, so a suite whose docstring promises the quota
#: cannot be exhausted went on certifying a daily run that could not complete — exactly as
#: ``LAUNCH_SATURDAY_FIXTURES = 131`` did one constant earlier.
#:
#: What keeps these honest is not their value but the tripwires in
#: ``tests/test_request_budget.py``, which read the fixture pool out of the database and
#: turn red when reality outgrows them.
MEASURED_UK_CATALOGUE = 67
MEASURED_PLAYED_CATALOGUE = 41
MEASURED_DAILY_WALK = 23


def is_played(competition_id: str) -> bool:
    """Whether this deployment draws fixtures from ``competition_id``.

    Three rules, in order:

    1. **Ireland is not played.** Neither division of it.
    2. **``england-amateur-*`` is not played, except the National Leagues.** That removes
       the FA Trophy, the Isthmian and Northern Premier and both Southern League Premier
       Divisions, the women's Super Leagues and every U21 competition — and keeps National
       League North and National League South.
    3. **Everything else is played** — England's four professional tiers and the National
       League, Scotland's four plus the Highland League and the cups, and Wales.

    Case- and whitespace-insensitive because the value is the provider's, not ours. An
    empty id is not played: nothing can be drawn from a competition with no identity.
    """
    slug = competition_id.strip().casefold()
    if not slug:
        return False
    if slug.startswith(_IRISH_PREFIXES):
        return False
    if slug.startswith(_ENGLAND_AMATEUR_PREFIX):
        tail = slug[len(_ENGLAND_AMATEUR_PREFIX) :]
        return bool(_NATIONAL_LEAGUE_DIVISION.match(tail))
    return True


def played(competition_ids: Iterable[str]) -> list[str]:
    """``competition_ids`` narrowed to the played ones, order preserved."""
    return [value for value in competition_ids if is_played(value)]


# ── Fantasy's European top flights (Batch 255) ──────────────────────────────────
#
# Owner decision, 26 Nov 2026: Fantasy also plays the Spanish, Italian, German and French
# top flights, for every two-game league, with no per-league switch ("lets go with one
# rule and not have the switch"). Group and legacy rounds stay British.
#
# A list here, not a rule like the trim above, because it is four deliberate choices
# rather than a classification of a catalogue that grows: the trim keeps a competition
# the provider adds next season, and this must not take Spain's second tier because it
# begins with ``spain-``. The slugs are the provider's own, **read from the live
# catalogue on 2026-11-11** and confirmed by the live 28 Nov census on 2026-11-26 (31
# fixtures in the Fantasy window, every one priced by Betfair Sportsbook in the sample).

#: The census keeps a British competition by this prefix (and :func:`is_played`).
UK_SLUG_PREFIXES: tuple[str, ...] = ("england-", "scotland-", "wales-", "northern-ireland-")

#: Played by Fantasy alone, whatever a league's own (British) competition list says.
FANTASY_ONLY_COMPETITIONS: frozenset[str] = frozenset(
    {
        "spain-laliga",
        "italy-serie-a",
        "germany-bundesliga",
        "france-ligue-1",
    }
)


def is_fantasy_only(competition_id: str) -> bool:
    """Whether ``competition_id`` is one of Fantasy's European top flights."""
    return competition_id.strip().casefold() in FANTASY_ONLY_COMPETITIONS


def census_keeps(competition_id: str) -> bool:
    """Whether the weekend census keeps an event from ``competition_id``.

    The played British competitions, as before, plus Fantasy's four. Everything else the
    one global page carries — some 2,400 events a weekend — is dropped as it always was.
    """
    slug = competition_id.strip().casefold()
    return (slug.startswith(UK_SLUG_PREFIXES) and is_played(slug)) or is_fantasy_only(slug)


def plays_competition(kind: str, competition_id: str, selected: frozenset[str] | None) -> bool:
    """Whether a ``kind`` game (``legacy``, ``group`` or ``fantasy``) plays a competition.

    ``selected`` is the league's own list (:func:`~src.services.gameweek.
    selected_competition_slugs`; ``None`` = every played British competition). The four
    European top flights belong to Fantasy alone and ignore that list: the list is chosen
    from a British catalogue, so it can neither include nor exclude them. Every other
    competition follows the list exactly as it did before this batch.

    The one rule the census, discovery, the game reads and the save all apply, so a
    fixture a card shows is a fixture its save accepts.
    """
    if is_fantasy_only(competition_id):
        return kind == "fantasy"
    return selected is None or competition_id in selected
