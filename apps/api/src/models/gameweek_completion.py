import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GameweekCompletion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The one instant a round's coupon filled up, made durable. Batch 107.

    Every other pick alert is fire-and-forget: it describes a thing the screen already
    says, so a lost push costs a member nothing they cannot see by looking. "All picks
    are in" is different in two ways, and both of them need a row.

    **It must not be sent twice.** Two members claiming the last two selections seconds
    apart both commit, and both then read ``12/12``. Deciding "am I the one who
    completed it?" from that read is a race with no winner — both are true. The unique
    key on ``gameweek_id`` moves the decision into the database: the insert that lands
    is the completing transition and the insert that conflicts is not, whatever order
    the two requests interleave in.

    **It must not be silently lost.** The completion is the moment the coupon becomes
    worth copying, and unlike a pick alert there is no second one coming — it happens
    once a round. Delivery is eleven blocking webpush calls on somebody's request path,
    so it can fail for reasons that have nothing to do with this league. ``delivered_at``
    stays ``NULL`` until a fan-out actually completes, and the next submission on the
    round claims and retries it.

    The picker, selection and price are **frozen onto the row** rather than re-read at
    delivery. A retry can run after that member has moved their pick, and the event is
    what happened at the transition — the alert has to still name the person who
    actually filled the coupon.
    """

    __tablename__ = "gameweek_completions"
    __table_args__ = (UniqueConstraint("gameweek_id", name="uq_gameweek_completions_gameweek"),)

    gameweek_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gameweeks.id", ondelete="CASCADE"), nullable=False
    )
    #: Who completed it. ``SET NULL`` rather than ``CASCADE``: a deleted profile must not
    #: take the round's completion event with it, and ``final_picker_name`` below is what
    #: the alert actually reads.
    final_picker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    #: The name *this league* knew them by at the transition — the membership override
    #: when they set one, matching the leaderboard and the ordinary pick alert.
    final_picker_name: Mapped[str] = mapped_column(String(100), nullable=False)
    #: ``Pick.runner_name`` as it stood at the transition; same width as the column it
    #: is copied from.
    selection: Mapped[str] = mapped_column(String(120), nullable=False)
    #: ``Pick.odds_at_pick`` — the frozen price, never a live quote, because a winner is
    #: scored on this number.
    odds: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    #: Active members at the transition, which is both halves of the ``12/12`` the alert
    #: prints. Stored so a retry cannot quote a denominator that has since moved.
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: ``NULL`` until a fan-out has finished. This is the retry flag and the
    #: already-announced flag at once.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
