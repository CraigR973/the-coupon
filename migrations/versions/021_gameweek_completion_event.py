"""The round filled up, recorded once and kept until it has been announced

Batch 107. The product has notified every pick since Batch 76 and never notified the one
moment members actually wait for: the round going ``12/12``, when the coupon stops being a
land-grab and becomes a thing to copy and place. That event is now sent — and unlike a pick
alert it needs somewhere to live.

**Why a table and not another fire-and-forget push.** Two reasons, and each on its own would
be enough:

* *Exactly once.* The last two members can claim seconds apart. Both commits land, and both
  requests then read ``12/12`` — so "did I complete it?" cannot be answered from that read,
  because for both of them the honest answer is yes. ``uq_gameweek_completions_gameweek``
  answers it instead: the insert that lands is the completing transition, the insert that
  conflicts is an ordinary pick, and the database decides regardless of interleaving.
* *Not silently lost.* Delivery is blocking webpush calls on a member's request path and
  can fail for reasons that have nothing to do with this league. A pick alert lost that way
  costs nothing — the screen already says it, and another pick is along in a minute. The
  completion happens once a round. ``delivered_at`` stays ``NULL`` until a fan-out finishes,
  and the next submission on that round claims the row and retries it.

**Frozen, not re-read.** ``final_picker_name``, ``selection``, ``odds`` and ``member_count``
are copied onto the row at the transition. A retry can run after that member has moved their
pick or after somebody has left the league, and the alert has to still name the person who
actually filled the coupon and the count that was true when it filled.

**Shape.** One row per completed round, no history: a round completes once, and a change of
pick afterwards is an ordinary pick at ``12/12`` rather than a second completion.
``ON DELETE CASCADE`` from ``gameweeks`` because the event has no meaning without the round;
``ON DELETE SET NULL`` from ``profiles`` because a deleted member must not take a league's
completion event with them, and the name the alert reads is on the row anyway.

**Recovery.** Nothing reads this table except the completion trigger, and an empty table
means "no round has been announced complete yet". A rollback therefore loses only the record
that past rounds were announced; it cannot corrupt a pick, a score or a standing. Its one
visible cost is that a round which completed before the downgrade would be announced again
if a member changed their pick afterwards — one duplicate push per affected round, which is
why the downgrade is safe to run and still not free.

Revision ID: 021
Revises: 020
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gameweek_completions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "gameweek_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("gameweeks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "final_picker_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("final_picker_name", sa.String(100), nullable=False),
        sa.Column("selection", sa.String(120), nullable=False),
        sa.Column("odds", sa.Numeric(6, 2), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=False), nullable=True),
        sa.UniqueConstraint("gameweek_id", name="uq_gameweek_completions_gameweek"),
    )

    # ── Supabase lockdown for the new table (mirrors 003/004/009/011/018) ────
    # The row carries a member's display name and their frozen price, which is league
    # members' business and nobody else's — the anon key must not be able to read it.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                ALTER TABLE public.gameweek_completions ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.gameweek_completions FORCE ROW LEVEL SECURITY;
                REVOKE ALL PRIVILEGES ON TABLE public.gameweek_completions
                    FROM anon, authenticated;
                DROP POLICY IF EXISTS deny_anon_authenticated ON public.gameweek_completions;
                CREATE POLICY deny_anon_authenticated ON public.gameweek_completions
                    AS RESTRICTIVE FOR ALL TO anon, authenticated
                    USING (false) WITH CHECK (false);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("gameweek_completions")
