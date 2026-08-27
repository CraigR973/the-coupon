"""The display-name backstop matches the check it is meant to back up

Batch 83. ``/auth/register`` pre-checks display-name uniqueness *case-insensitively*
— ``lower(display_name) = lower(:name)`` — because "Dave" and "dave" are one person
twice on a leaderboard, which is precisely the impersonation an open signup invites.
The comment in that handler called ``uq_profiles_display_name`` the backstop for the
pre-check losing a race.

It was not. ``uq_profiles_display_name`` (001, ``sa.UniqueConstraint("display_name")``)
is **case-sensitive**, so it only ever caught an exact-case race. Two concurrent
registrations for "Dave" and "dave" both read *not taken*, both satisfied the
constraint at flush, and both committed — no ``IntegrityError``, and the duplicate
identity the pre-check exists to prevent, written to the leaderboard. Only a live
scenario since Batch 63 opened unauthenticated self-registration; before that,
accounts were provisioned one at a time by the owner.

This swaps the constraint for a functional unique index on ``lower(display_name)``:

* ``uq_profiles_display_name`` is dropped;
* ``uq_profiles_display_name_lower`` — ``UNIQUE (lower(display_name))`` — replaces it.

The new index **subsumes** the old one: if the lowered form is unique then the raw
form is too, so nothing that was rejected before is accepted now. The reverse is the
point — a case-variant collision is now refused by Postgres, whichever process gets
there second, with no reliance on the application winning a race with itself.

**Every row is covered, including soft-deleted ones.** The index is not partial,
matching the pre-check's own deliberate refusal to filter on ``deleted_at``:
a departed member's name stays reserved, because handing a stranger the identity a
league's whole history is written against would be worse than making them choose
another name.

**The upgrade fails if two existing profiles already differ only by case**, and it
fails *before* touching anything, naming the rows. That is correct rather than
unfortunate — those two rows are the defect, and no migration can pick which one is
the real member. Rename or delete one, then upgrade.

The check is written out by hand rather than left to the unique violation Postgres
would raise anyway, because this runs on boot: a raw ``duplicate key value violates
unique constraint`` in a container log says nothing about which member to fix, and
the service stays down until someone works it out. The explicit form names them.

**This was not verified against production before shipping.** It could not be: the
production Postgres host resolves to IPv6 only and this workstation has no IPv6
route, and the project's REST API is answering 402 under the egress quota noted on
2026-08-25. The runtime check above is what stands in for that verification — the
worst case is a refused boot with a message naming the two rows, recoverable by
renaming one and redeploying, rather than a silently merged identity.

No Supabase lockdown block: ``profiles`` already has RLS forced by 003/004, and an
index inherits its table's policies (see 014, 015).

Revision ID: 017
Revises: 016
Create Date: 2026-08-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _refuse_existing_collisions()
    # Order matters: create the stricter index first, so there is no instant in which
    # the table holds no uniqueness rule at all. A registration landing between the two
    # statements is still refused.
    op.create_index(
        "uq_profiles_display_name_lower",
        "profiles",
        [sa.text("lower(display_name)")],
        unique=True,
    )
    op.drop_constraint("uq_profiles_display_name", "profiles", type_="unique")


def _refuse_existing_collisions() -> None:
    """Stop with a message naming the rows, rather than a bare unique violation."""
    collisions = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT lower(display_name) AS lowered, count(*) AS n, "
                "       string_agg(id::text, ', ' ORDER BY created_at) AS ids "
                "FROM profiles GROUP BY 1 HAVING count(*) > 1 ORDER BY 1"
            )
        )
        .all()
    )
    if not collisions:
        return
    detail = "; ".join(f"{row.lowered!r} held by {row.n} profiles ({row.ids})" for row in collisions)
    raise RuntimeError(
        "Migration 017 cannot make display names case-insensitively unique while "
        f"profiles already collide: {detail}. Rename or delete all but one of each "
        "group, then run this migration again. It has changed nothing."
    )


def downgrade() -> None:
    op.create_unique_constraint("uq_profiles_display_name", "profiles", ["display_name"])
    op.drop_index("uq_profiles_display_name_lower", table_name="profiles")
