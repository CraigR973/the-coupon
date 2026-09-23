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

from fastapi import HTTPException, status

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
    return name
