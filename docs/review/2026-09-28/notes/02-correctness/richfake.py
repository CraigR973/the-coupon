"""A deterministic, richer FakeBetfair for the lens-02 correctness pass.

Both the API process (corr_server.py) and the in-process driver scripts build it from
this one function, so provider event ids, market ids and prices agree across processes.
Nothing here can reach a live provider: it subclasses the repo's own FakeBetfair.

Card (UK local kick-offs):
  Fri  2 Oct 2026 19:45 BST   4 fixtures (EPL x2, Championship, Scottish Prem)
  Sat  3 Oct 2026 15:00 BST   6 fixtures (EPL x2, Championship x2, Scottish Prem x2)
  Fri  9 Oct / Sat 10 Oct     same shape
  Fri 23 Oct 19:45 BST, Sat 24 Oct 15:00 BST, Sun 25 Oct 13:00 GMT (the clocks go back)
  Fri 30 Oct 19:45 GMT, Sat 31 Oct 15:00 GMT
A counting wrapper records every primitive call for the budget checks.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, "/Users/craigrobinson/the-coupon/apps/api")

from src.services.betfair import (  # noqa: E402
    MARKET_BTTS,
    MARKET_MATCH_ODDS,
    BFCompetitionResult,
    BFEventResult,
    BFMarketBook,
    BFMarketCatalogue,
    BFRunnerBook,
    FakeBetfair,
)

UK = ZoneInfo("Europe/London")

COMPS = {
    "england-premier-league": "English Premier League",
    "england-championship": "English Championship",
    "scotland-premiership": "Scottish Premiership",
}

# (date, local hh:mm, [competition ids in order])
CARD: list[tuple[date, str, list[str]]] = [
    (date(2026, 10, 2), "19:45", ["england-premier-league"] * 2 + ["england-championship", "scotland-premiership"]),
    (date(2026, 10, 3), "15:00", ["england-premier-league"] * 2 + ["england-championship"] * 2 + ["scotland-premiership"] * 2),
    (date(2026, 10, 9), "19:45", ["england-premier-league"] * 2 + ["england-championship", "scotland-premiership"]),
    (date(2026, 10, 10), "15:00", ["england-premier-league"] * 2 + ["england-championship"] * 2 + ["scotland-premiership"] * 2),
    (date(2026, 10, 23), "19:45", ["england-premier-league"] * 2 + ["england-championship", "scotland-premiership"]),
    (date(2026, 10, 24), "15:00", ["england-premier-league"] * 2 + ["england-championship"] * 2 + ["scotland-premiership"] * 2),
    (date(2026, 10, 25), "13:00", ["england-premier-league", "england-championship"]),
    (date(2026, 10, 30), "19:45", ["england-premier-league"] * 2 + ["england-championship", "scotland-premiership"]),
    (date(2026, 10, 31), "15:00", ["england-premier-league"] * 2 + ["england-championship"] * 2 + ["scotland-premiership"] * 2),
]

TEAMS = [
    "Arsenal", "Chelsea", "Everton", "Fulham", "Brentford", "Wolves", "Leeds", "Burnley",
    "Hibs", "Hearts", "Celtic", "Rangers", "Stoke", "Hull", "Derby", "Luton", "Aberdeen",
    "Motherwell", "Millwall", "Watford", "Bristol City", "Coventry", "Kilmarnock", "Dundee",
]

# A price ladder the fixtures cycle through: home, draw, away, btts yes, btts no.
PRICES = [
    (1.9, 3.75, 4.3, 1.8, 2.05),
    (2.4, 3.2, 3.1, 1.95, 1.85),
    (1.6, 4.0, 5.5, 2.1, 1.7),
    (2.8, 3.3, 2.6, 1.75, 2.1),
    (3.6, 3.5, 2.05, 1.9, 1.9),
    (1.33, 5.0, 9.0, 2.2, 1.65),
]

HOME, DRAW, AWAY, YES, NO = 1, 3, 2, 30246, 58948


def event_id(day: date, n: int) -> str:
    return f"rf-{day:%m%d}-{n}"


def market_ids(eid: str) -> tuple[str, str]:
    return f"{eid}-mo", f"{eid}-btts"


def fixtures() -> list[dict[str, Any]]:
    out = []
    t = 0
    for day, hhmm, comps in CARD:
        hh, mm = (int(x) for x in hhmm.split(":"))
        local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=UK)
        z = local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        for n, comp in enumerate(comps):
            home, away = TEAMS[t % len(TEAMS)], TEAMS[(t + 1) % len(TEAMS)]
            t += 2
            out.append(
                {
                    "id": event_id(day, n),
                    "name": f"{home} v {away}",
                    "home": home,
                    "away": away,
                    "comp": comp,
                    "openDate": z,
                    "prices": PRICES[n % len(PRICES)],
                }
            )
    return out


def build() -> FakeBetfair:
    comps = [
        BFCompetitionResult.model_validate({"competition": {"id": cid, "name": name}, "marketCount": 9})
        for cid, name in COMPS.items()
    ]
    events: dict[str, list[BFEventResult]] = {cid: [] for cid in COMPS}
    catalogues: list[BFMarketCatalogue] = []
    books: list[BFMarketBook] = []
    for f in fixtures():
        ev = {"id": f["id"], "name": f["name"], "countryCode": "GB", "openDate": f["openDate"]}
        events[f["comp"]].append(BFEventResult.model_validate({"event": ev, "marketCount": 2}))
        mo, btts = market_ids(f["id"])
        h, d, a, y, no = f["prices"]
        catalogues.append(
            BFMarketCatalogue.model_validate(
                {
                    "marketId": mo,
                    "marketName": "Match Odds",
                    "description": {"marketType": MARKET_MATCH_ODDS},
                    "event": ev,
                    "runners": [
                        {"selectionId": HOME, "runnerName": f["home"], "sortPriority": 1},
                        {"selectionId": AWAY, "runnerName": f["away"], "sortPriority": 2},
                        {"selectionId": DRAW, "runnerName": "The Draw", "sortPriority": 3},
                    ],
                }
            )
        )
        catalogues.append(
            BFMarketCatalogue.model_validate(
                {
                    "marketId": btts,
                    "marketName": "Both teams to Score",
                    "description": {"marketType": MARKET_BTTS},
                    "event": ev,
                    "runners": [
                        {"selectionId": YES, "runnerName": "Yes", "sortPriority": 1},
                        {"selectionId": NO, "runnerName": "No", "sortPriority": 2},
                    ],
                }
            )
        )
        for mid, prices in ((mo, {HOME: h, AWAY: a, DRAW: d}), (btts, {YES: y, NO: no})):
            books.append(
                BFMarketBook.model_validate(
                    {
                        "marketId": mid,
                        "status": "OPEN",
                        "runners": [
                            {
                                "selectionId": sid,
                                "status": "ACTIVE",
                                "ex": {"availableToBack": [{"price": p, "size": 100.0}]},
                            }
                            for sid, p in prices.items()
                        ],
                    }
                )
            )
    return CountingFake(competitions=comps, events=events, catalogues=catalogues, books=books)


class CountingFake(FakeBetfair):
    """FakeBetfair that counts every primitive, and can settle a fixture by score or void."""

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.calls: Counter[str] = Counter()

    async def list_competitions(self, **kw: Any):  # type: ignore[override]
        self.calls["list_competitions"] += 1
        return await super().list_competitions(**kw)

    async def list_events(self, **kw: Any):  # type: ignore[override]
        self.calls["list_events"] += 1
        return await super().list_events(**kw)

    async def list_market_catalogue(self, **kw: Any):  # type: ignore[override]
        self.calls["list_market_catalogue"] += 1
        return await super().list_market_catalogue(**kw)

    async def list_market_book(self, **kw: Any):  # type: ignore[override]
        self.calls["list_market_book"] += 1
        return await super().list_market_book(**kw)

    def result(self, eid: str, home_goals: int, away_goals: int) -> None:
        """Close both markets of one fixture from a scoreline."""
        mo, btts = market_ids(eid)
        winner = HOME if home_goals > away_goals else AWAY if away_goals > home_goals else DRAW
        self.close_markets({mo: winner, btts: YES if home_goals and away_goals else NO})

    def void(self, eid: str) -> None:
        """Close both markets with every runner REMOVED: every pick on it voids."""
        for mid in market_ids(eid):
            book = self._books[mid]
            self._books[mid] = BFMarketBook(
                marketId=mid,
                status="CLOSED",
                runners=[BFRunnerBook(selectionId=r.selectionId, status="REMOVED", ex=r.ex) for r in book.runners],
            )

    def reprice(self, eid: str, selection_id: int, price: float, market: str = "mo") -> None:
        mid = f"{eid}-{market}"
        book = self._books[mid]
        runners = []
        for r in book.runners:
            data = r.model_dump()
            if r.selectionId == selection_id:
                data["ex"] = {"availableToBack": [{"price": price, "size": 100.0}]}
            runners.append(data)
        self._books[mid] = BFMarketBook.model_validate(
            {"marketId": mid, "status": book.status, "runners": runners}
        )


if __name__ == "__main__":
    for f in fixtures():
        print(f["id"], f["openDate"], f["comp"], f["name"], f["prices"])
