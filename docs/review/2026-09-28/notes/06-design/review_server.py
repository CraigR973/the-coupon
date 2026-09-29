"""Lens 06's API: the e2e server plus one test-only endpoint that moves a fake price.

Why: the brief asks for the price-moved pick feedback to be driven for real — the fake
provider moving a price between the card load and the tap — and tests.e2e_server has no
hook for it. This module imports that app unchanged and adds

    POST /__review/move-price?market_id=1.100000001&selection_id=1001&price=2.64

which rebuilds that runner's best back price on the live FakeBetfair instance
(`tests.e2e_server.fake_betfair`, the object the dependency override returns at call
time). The pick path then fetches the moved price and refuses with PRICE_MOVED:<new>.
Nothing else changes. Served only by notes/06-design/stack_design.py, on a scratch DB.
"""

from __future__ import annotations

from fastapi import HTTPException

import tests.e2e_server as e2e
from src.services.betfair import BFExchangePrices, BFPriceSize
from tests.e2e_server import app  # noqa: F401  (re-exported for uvicorn)


@app.post("/__review/move-price")
async def move_price(market_id: str, selection_id: int, price: float) -> dict[str, object]:
    fb = e2e.fake_betfair
    book = fb._books.get(market_id)
    if book is None:
        raise HTTPException(status_code=404, detail="NO_SUCH_MARKET")
    runners = []
    moved = False
    for r in book.runners:
        if r.selectionId == selection_id:
            r = r.model_copy(
                update={"ex": BFExchangePrices(availableToBack=[BFPriceSize(price=price, size=120.0)])}
            )
            moved = True
        runners.append(r)
    if not moved:
        raise HTTPException(status_code=404, detail="NO_SUCH_SELECTION")
    fb._books[market_id] = book.model_copy(update={"runners": runners})
    return {"market_id": market_id, "selection_id": selection_id, "price": price}


@app.get("/__review/books")
async def books() -> dict[str, object]:
    fb = e2e.fake_betfair
    return {
        m: [
            {"sel": r.selectionId, "price": (r.ex.availableToBack[0].price if r.ex and r.ex.availableToBack else None)}
            for r in b.runners
        ]
        for m, b in fb._books.items()
    }
