"""A member can exist without a credential, between an admin reset and their next sign-in

Batch 66. Until now the only way back in for a member who had forgotten their PIN
was for an admin to mint a temporary one and read it out — a secret passing
through a third person, reusable, and shareable. The owner's decision (2026-08-23)
is that an admin reset **clears** the credential instead and the member chooses
their own at the next sign-in, so no interim value exists to be leaked.

"Clears" is only expressible if the column admits it:

* ``profiles.pin_hash`` drops ``NOT NULL``. ``NULL`` means *this account has no
  credential and cannot be signed into until one is set* — it is not a weaker
  PIN, it is the absence of one, and ``src/routers/auth.py`` refuses a login
  against it outright rather than falling through to bcrypt.

No data moves. Every existing row keeps its hash, and the constraint is only
relaxed, so this is safe to run against a live database with picks in flight.

**The downgrade can fail, and that is correct.** ``SET NOT NULL`` is refused
while any profile is mid-reset. Restoring the constraint means deciding what
those members' credential should be, and inventing one here — a hash nobody
knows, or worse, one somebody could guess — would be exactly the failure this
migration exists to remove. Set a PIN for them, or delete them, then downgrade.

No Supabase lockdown block: ``profiles`` already has RLS forced by 003/004, and
altering a column inherits the table's policies (see 015).

Revision ID: 016
Revises: 015
Create Date: 2026-08-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "profiles",
        "pin_hash",
        existing_type=sa.String(length=60),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "profiles",
        "pin_hash",
        existing_type=sa.String(length=60),
        nullable=False,
    )
