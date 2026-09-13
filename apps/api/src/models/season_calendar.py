from datetime import date

import sqlalchemy as sa
from sqlalchemy import Date, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UpdatedAtMixin


class SeasonCalendar(Base, UpdatedAtMixin):
    """The deployment-wide football calendar for one season.

    ``week_one_anchor`` is the canonical Saturday called week 1. It is written once
    from the first round the deployment holds and is never recomputed merely because an
    earlier round appears later. ``extra_weeks`` are global dates: discovery offers each
    one to every active league through that league's own window and competition filter.
    """

    __tablename__ = "season_calendars"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_one_anchor: Mapped[date] = mapped_column(Date, nullable=False)
    extra_weeks: Mapped[list[date]] = mapped_column(
        ARRAY(Date), nullable=False, default=list, server_default=sa.text("ARRAY[]::date[]")
    )
