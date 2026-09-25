"""The one set of rules a name has to satisfy before anybody sees it.

Registration has enforced these since Batch 63. The per-league display-name override
did not: it stored whatever it was sent, bounded only by the column's 100 characters —
no charset, no normalisation, and no uniqueness at all. The roster, the standings and
the coupon all render the override, so two members could appear under one name, and the
owner's text-only decision makes the name the whole of a member's identity here.

Batch 126 moved the rules here so the second path reuses them rather than restating
them. Nothing about registration changes; `routers/auth.py` keeps its own names as
aliases onto these.
"""

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, SQLColumnExpression, case, literal

#: 2-32 rather than the column's 100. The name is the login identifier *and* what every
#: leaderboard row, roster entry and push message renders, so the practical ceiling is
#: what fits those, not what Postgres will hold.
MIN_DISPLAY_NAME_LENGTH = 2
MAX_DISPLAY_NAME_LENGTH = 32

#: Letters, digits, and the punctuation that appears in real names. Must *open* with a
#: letter or digit so a name cannot be padded into sorting first or made to look like UI
#: chrome. Deliberately no control characters, no combining marks, no emoji.
DISPLAY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._'-]*$")

LENGTH_ERROR = (
    f"Display name must be {MIN_DISPLAY_NAME_LENGTH}-{MAX_DISPLAY_NAME_LENGTH} characters."
)
CHARSET_ERROR = (
    "Display name can use letters, numbers, spaces, and . _ ' - "
    "and must start with a letter or number."
)

#: Batch 136. What a member who deleted their account is called wherever members see them.
FORMER_MEMBER = "Former member"

#: What is stored in their place: unique, as ``profiles.display_name`` must be, and naming
#: nobody. Read paths map it to :data:`FORMER_MEMBER`; one that does not shows this, never
#: the name — the overwrite is the privacy guarantee and the mapping is presentation.
_PLACEHOLDER = re.compile(r"^Former member [0-9a-f]{8}$")
_PLACEHOLDER_SQL = "^Former member [0-9a-f]{8}$"

#: Nobody may take a name that would read as a deleted member's — on a leaderboard it
#: would pass for them.
RESERVED_PREFIX = FORMER_MEMBER.casefold()
RESERVED_ERROR = "That name is reserved."


def is_reserved(name: str) -> bool:
    return name.casefold().startswith(RESERVED_PREFIX)


def former_member_placeholder() -> str:
    return f"{FORMER_MEMBER} {uuid.uuid4().hex[:8]}"


def public_name(name: str) -> str:
    """A name as members see it: a deleted member's placeholder reads "Former member"."""
    return FORMER_MEMBER if _PLACEHOLDER.match(name) else name


def public_name_sql(name: SQLColumnExpression[str]) -> ColumnElement[str]:
    """:func:`public_name` inside a query, so a table's rows arrive already labelled."""
    return case((name.op("~")(_PLACEHOLDER_SQL), literal(FORMER_MEMBER)), else_=name)


def normalise_display_name(raw: str) -> str:
    """Trim, and collapse internal runs of whitespace to single spaces.

    Two names differing only by padding are the same name to every human reading a
    leaderboard, so they must not be able to coexist. Normalising here means a
    uniqueness check and the stored value agree.
    """
    return " ".join(raw.split())


def validated_display_name(raw: str) -> str:
    """The normalised name, or a 422 saying which rule it broke."""
    name = normalise_display_name(raw)
    if not (MIN_DISPLAY_NAME_LENGTH <= len(name) <= MAX_DISPLAY_NAME_LENGTH):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=LENGTH_ERROR)
    if not DISPLAY_NAME_RE.match(name):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=CHARSET_ERROR)
    if is_reserved(name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=RESERVED_ERROR
        )
    return name
