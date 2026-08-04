"""Rename the provider-named odds columns off Betfair

ADR 0002 replaced the Betfair Exchange with odds-api.io, so three columns named
after the old provider had to change:

* ``fixtures.betfair_event_id`` → ``fixtures.provider_event_id``, widened to 64
  characters because odds-api.io identifiers are not Betfair's short numeric ids.
  The unique constraint ``uq_fixtures_gameweek_event`` depends on this column;
  PostgreSQL carries a constraint through a column rename, so it needs no
  rebuild and keeps its name.
* ``picks.betfair_market_id`` and ``picks.betfair_selection_id`` are **dropped**.
  odds-api.io has no per-selection identifier, so neither had a natural value —
  and neither was needed: ``uq_picks_league_gameweek_selection`` already
  identifies a pick by ``(league, gameweek, fixture, market, outcome)``, which is
  exactly what settlement now resolves against. Keeping a synthesised id would
  have re-encoded a provider's shape in the schema for no gain.

Forward-only and safe on populated tables. The rename preserves every existing
row; the two drops discard columns that no longer have a meaning under the new
provider. Production holds one bootstrapped administrator and no fixtures or
picks (Betfair refused the production login, so none could ever be created), so
nothing scored is lost here.

There is no downgrade: restoring the dropped columns would mean inventing
Betfair identifiers that no longer exist anywhere.

Revision ID: 005
Revises: 004
Create Date: 2026-08-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "fixtures",
        "betfair_event_id",
        new_column_name="provider_event_id",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    op.drop_column("picks", "betfair_selection_id")
    op.drop_column("picks", "betfair_market_id")


def downgrade() -> None:
    raise NotImplementedError(
        "005 is forward-only: the dropped Betfair identifiers cannot be reconstructed"
    )
