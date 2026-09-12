"""How the product names a selection, on the one surface that reaches a phone unprompted.

Batch 116, from the owner's live use of the alerts Batch 107 shipped. A pick alert
interpolated ``Pick.runner_name`` raw, and that string is composed from the *market*
alone: Match Odds gives a team name, but a draw gives ``The Draw`` and Both Teams To Score
gives the bare word ``Yes`` or ``No``. So a BTTS claim reached the league as

    Dave picked Yes @ 1.80 · 3/12 picked

— a price, a progress count, and no fixture. The alert exists because the coupon is a
land-grab and the rest of the league needs to know *what has gone*; on a BTTS or draw claim
it said something had gone and refused to say what. Half the selections the product offers
could not be named in an alert at all.

**The vocabulary already existed; the API did not have it.** ``lib/coupon.ts`` has rendered
``Both teams score (Forfar v Brechin)`` on every coupon row, pasted line and home card since
Batch 105. The alert is the one surface that never got it, because the API composes its own
copy — and the two had drifted, not merely diverged in coverage: the API said ``The Draw``
where the web says ``Draw`` and ``Yes`` where the web says ``Both teams score``. This module
is the API's half of one vocabulary, and it is written to match
``outcomeLabel`` / ``fixtureContext`` / ``selectionSummary`` line for line. **They must move
together**; a difference between them is a member reading two names for one thing.
"""

from __future__ import annotations

from src.models.pick import PickMarket, PickOutcome


def outcome_label(market: PickMarket, outcome: PickOutcome, home: str, away: str) -> str:
    """What the selection is called. Mirrors ``outcomeLabel`` in ``lib/coupon.ts``.

    Match Odds resolves ``HOME``/``AWAY`` to the team names, because the selection *is* one
    of the two teams; everything else is named by what it is. Deliberately **not**
    ``Pick.runner_name``: that is the provider's word for the runner, which is the same
    thing for a team and a useless one for anything else.
    """
    if market == PickMarket.MATCH_ODDS:
        if outcome == PickOutcome.HOME:
            return home
        if outcome == PickOutcome.AWAY:
            return away
        return "Draw"
    return "Both teams score" if outcome == PickOutcome.YES else "No — not both score"


def fixture_context(market: PickMarket, outcome: PickOutcome, home: str, away: str) -> str:
    """The fixture context a selection does not already carry. Mirrors ``fixtureContext``.

    Batch 105's rule, and the reason the alert must not simply append the whole fixture: a
    Match Odds selection already names one of the teams, so what disambiguates it is *the
    other one*. A draw or a Both-Teams-to-Score call names neither, so it takes the pairing.
    Printing "Arsenal · Arsenal v Chelsea" puts the one word a reader is scanning for on the
    row twice and pushes the price off the end of it.
    """
    if market == PickMarket.MATCH_ODDS:
        if outcome == PickOutcome.HOME:
            return f"v {away}"
        if outcome == PickOutcome.AWAY:
            return f"at {home}"
    return f"{home} v {away}"


def selection_summary(market: PickMarket, outcome: PickOutcome, home: str, away: str) -> str:
    """A selection and its disambiguating context as one phrase — ``Draw (Forfar v Brechin)``.

    Mirrors ``selectionSummary``. This is what a pick alert names, so that a member reading
    a tray entry and a member reading the coupon are reading the same words.
    """
    return (
        f"{outcome_label(market, outcome, home, away)} "
        f"({fixture_context(market, outcome, home, away)})"
    )
