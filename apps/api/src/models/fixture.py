from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class Fixture(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One real match, in a pool shared by every league.

    Mapped from a :class:`~src.services.odds_provider.SlateFixture`; ``home`` / ``away``
    are the team names the provider supplies directly (no separate Team table).

    **Pooled since Batch 14.** A fixture used to be owned by one gameweek
    (``gameweek_id``, unique per ``(gameweek, provider_event_id)``), which made the
    same match unrepresentable on two leagues' cards. Now a fixture is one row per
    real match — unique on ``provider_event_id`` alone — and leagues select it
    through :class:`~src.models.gameweek.GameweekFixture`. That is what keeps the
    provider cost flat as leagues are added: the match is fetched once regardless of
    how many leagues play it.

    Odds are not stored here — they are snapshotted onto each
    :class:`~src.models.pick.Pick` at pick time, so the offerable selections come
    live from the provider.

    ``provider_event_id`` is whatever the configured odds source calls this fixture.
    It was ``betfair_event_id`` until revision ``005``; the rename is what let the
    Exchange be swapped out without the schema still naming it.
    """

    __tablename__ = "fixtures"
    __table_args__ = (UniqueConstraint("provider_event_id", name="uq_fixtures_provider_event"),)

    provider_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    home: Mapped[str] = mapped_column(String(120), nullable=False)
    away: Mapped[str] = mapped_column(String(120), nullable=False)
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    competition: Mapped[str] = mapped_column(String(120), nullable=False)
    # Holds the provider's league slug, not a short numeric id as it did under
    # Betfair. Ten of the thirty UK slugs exceed 32 characters and the longest
    # across all competitions is 66, so this matches `competition`'s width.
    competition_id: Mapped[str] = mapped_column(String(120), nullable=False)

    # ── What the bookmaker will and will not price (Batch 114) ─────────────────
    #
    # Odds are still not stored here — these two say whether asking is worth a request.
    #
    # `odds_unpriced_since_utc` is set the first time a successful sweep comes back with
    # no selections for this fixture, and cleared the moment one comes back with any. It
    # is the deployment *learning* something durable: a bookmaker with no market on a
    # non-league cup tie will not have opened one by the next page load, and on 2026-09-05
    # 103 such fixtures cost half of every sweep and rendered as unpickable rows.
    #
    # `odds_checked_at_utc` is what stops that from being permanent. A marked fixture is
    # re-asked once `ODDS_UNPRICED_RECHECK_SECONDS` have passed, so a market opened late is
    # found and the row returns to the card.
    #
    # Only a sweep that actually reached the provider writes here. A degraded one is not
    # evidence of anything — see `routers/gameweek.py`.
    odds_unpriced_since_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    odds_checked_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
