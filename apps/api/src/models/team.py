import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin, UUIDPrimaryKeyMixin


class Team(Base, UUIDPrimaryKeyMixin, UpdatedAtMixin):
    """One club, as the football-data provider knows it (Batch 16).

    The product had no ``Team`` table at all: ``fixtures.home`` / ``away`` are free text
    straight from the odds provider, which is enough to price and settle a match but not
    to say where a club sits in its table or how its last five went.

    ``provider_team_id`` is the key, never the name. The two providers spell clubs
    differently — "Airdrieonians FC" against "Airdrieonians", "Nott'm Forest" against
    "Nottingham Forest" — so identity has to hang off an id, with the spellings handled
    as aliases (:class:`TeamAlias`).

    ``competition_id`` is the odds provider's slug for the competition this club was last
    seen in, not a foreign key: competitions are not a table, and a club moves between
    them on promotion. It scopes alias lookups, which is what keeps two clubs that
    normalise alike in different divisions from colliding.
    """

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("provider_team_id", name="uq_teams_provider_team"),
        Index("ix_teams_competition_normalised", "competition_id", "normalised_name"),
    )

    provider_team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    short_name: Mapped[str] = mapped_column(String(60), nullable=False, server_default="")
    #: ``name`` run through :func:`~src.services.team_matching.normalise_name`. Stored so
    #: reconciliation is an indexed lookup rather than a scan-and-normalise of every club.
    normalised_name: Mapped[str] = mapped_column(String(120), nullable=False)
    competition_id: Mapped[str] = mapped_column(String(120), nullable=False, server_default="")
    country: Mapped[str] = mapped_column(String(60), nullable=False, server_default="")


class TeamAlias(Base):
    """One spelling of a club, resolved to the club it means — the reconciliation layer.

    Every name The Coupon meets — the football provider's own, and the odds provider's
    free-text ``fixtures.home`` / ``away`` — is recorded here in normalised form. That
    turns matching into a primary-key lookup on the read path, and it makes the layer
    *auditable*: a wrong link is one visible row, correctable without touching code.

    Keyed by ``(competition_id, normalised)`` rather than ``normalised`` alone. Club names
    are only unique within a division — Bangor plays in both Wales and Northern Ireland —
    so a global key would either collide or force a name that is perfectly unambiguous in
    its own league to be disambiguated.

    ``source`` records how the link was made: ``provider`` (the football source's own
    name), ``odds`` (learned by matching an odds fixture) or ``manual``. Fuzzy matches are
    still ``odds``; the confidence that produced them is in the ingestion log, not here.
    """

    __tablename__ = "team_aliases"

    competition_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    normalised: Mapped[str] = mapped_column(String(120), primary_key=True)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    #: The spelling exactly as it was seen, kept for the audit trail.
    alias: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="provider")
