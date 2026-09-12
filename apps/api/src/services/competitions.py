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
  fixture pool on 2026-09-12, of the 33 competitions that have ever carried a fixture
  onto a round this removes **13** and keeps **20**.
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


#: What the provider carries and what this deployment plays of it, **measured live with
#: ``fetch_competitions`` on 2026-09-12** — 67 UK competitions in the catalogue, 41 of them
#: played after the trim, and 20 of *those* that have ever put a fixture in the pool and so
#: are what a daily walk actually costs.
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
MEASURED_DAILY_WALK = 20


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
