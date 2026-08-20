"""Profile pictures: where a member's avatar lives

Batch 42. The Coupon has never had avatars. The frontend once called
``/api/v1/auth/me/avatar`` against an API with no such route and no such field,
and the MVP action recorded in ``docs/LAUNCH_PLAN.md`` was to strip the upload
controls and keep initials. This is the column that was missing.

One additive, nullable column:

* ``profiles.avatar_url`` (varchar(500), nullable). Where the image lives, not the
  image: bytes belong in an object store, and the database only remembers the
  address. ``NULL`` is the ordinary state — every existing member, and every
  member who never sets one — and it reads as "use the initials fallback", which
  is exactly what every surface already did.

500 characters is chosen against signed object-store URLs, which carry a token
and a expiry in the query string and run far past the length a bare path needs.
A URL too long to store would fail the upload rather than truncate.

No Supabase lockdown block: ``profiles`` already has RLS forced by 003/004, and a
column inherits its table's policies. Only a brand-new table needs the block
(009, 011).

**This migration does not enable avatars.** The upload path is gated on an
object-store backend that is not configured in any environment, and the endpoint
fails closed until one is (see ``src/services/avatar_storage.py``). The column is
here so the read surfaces stop hardcoding ``None`` and the shape is settled; the
storage decision, its access rules, and server-side re-encoding are deliberately
still open.

Revision ID: 015
Revises: 014
Create Date: 2026-08-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("avatar_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "avatar_url")
