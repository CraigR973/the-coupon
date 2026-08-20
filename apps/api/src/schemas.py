"""Shared wire types for the API's response models.

Every instant this application stores is **naive UTC** — the columns are
``TIMESTAMP WITHOUT TIME ZONE``, the services compare naive to naive, and that
is internally consistent and correct. It stops being correct at the wire:
pydantic serialises a naive datetime as ``"2026-08-22T13:30:00"``, and
JavaScript's ``Date`` parses a date-time string carrying no offset as **local**
time. A 13:30 UTC lock — 14:30 in London under BST — therefore arrived in the
browser as 13:30 local, an hour early, and ``useCountdown`` shut the pick screen
an hour before the API stopped accepting picks (Batch 43).

The fix belongs here rather than at each ``new Date(...)`` in the client,
because this corrects every consumer at once — the web app, a future client, and
anything reading the API directly — where patching call sites corrects only the
ones someone remembers.

Annotate every datetime a response model carries with :data:`UtcDatetime`.
``tests/test_wire_datetimes.py`` walks the app's routes and fails if one is
missed, which is what keeps this true for models written later.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def stamp_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC instant, assuming UTC when it is naive.

    Assuming UTC is not a guess: every datetime column in this schema is written
    in UTC (see ``src/services/gameweek.py``'s ``_naive_utc``), so a naive value
    reaching here is UTC that lost its label somewhere between the column and
    the response model.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# Serialises as ``2026-08-22T13:30:00Z`` rather than ``2026-08-22T13:30:00``.
#
# The offset is pydantic's own rendering of an aware UTC datetime, so the field
# stays a `datetime` in OpenAPI (`format: date-time`) and in a Python-mode
# `model_dump()`; only the JSON gains the `Z`. `Z` and `+00:00` are the same
# instant to every parser that matters — `Date`, `date-fns`, `datetime.fromisoformat`
# on 3.11+ — and `Z` is what pydantic emits without a bespoke string serialiser.
UtcDatetime = Annotated[datetime, PlainSerializer(stamp_utc, return_type=datetime)]
