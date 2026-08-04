"""Widen fixtures.competition_id for odds-api.io league slugs

Migration 005 widened ``fixtures.provider_event_id`` for the new provider's
event identifiers but left ``fixtures.competition_id`` at ``String(32)``. That
column held Betfair's short numeric competition ids — ``"105"`` for the Scottish
Premiership — and now holds an odds-api.io league *slug*.

Ten of the thirty UK league slugs exceed 32 characters, the longest being
``england-amateur-southern-league-premier-division-central`` at 56, and the
longest across all 728 competitions is 66. The slate is written in a single
transaction, so this did not merely drop the affected leagues: the first
oversized slug aborted the whole refresh with

    StringDataRightTruncationError: value too long for type character varying(32)

and production could not build any slate at all.

Widened to 120 to match ``fixtures.competition``, which already stores the
human-readable league name from the same payload. 64 would not have been
enough for the 66-character maximum.

Widening a ``varchar`` is a metadata-only change in PostgreSQL, so this does not
rewrite the table and is safe on populated tables. Production holds no fixtures
at this revision, because the bug prevented any from being created.

Revision ID: 006
Revises: 005
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "fixtures",
        "competition_id",
        existing_type=sa.String(32),
        type_=sa.String(120),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Narrowing again would truncate any slug longer than 32 characters, which
    # is most of the English amateur tiers.
    op.alter_column(
        "fixtures",
        "competition_id",
        existing_type=sa.String(120),
        type_=sa.String(32),
        existing_nullable=False,
    )
