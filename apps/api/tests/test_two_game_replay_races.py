"""Accepted receipts outrank mutable refusals at independent transaction handoffs."""

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from src.config import settings
from src.models.league import League
from src.models.league_membership import LeagueMembership
from src.models.ledger import LedgerEntry, LedgerKind
from src.models.two_game import (
    FantasyPick,
    GameOperation,
    GroupPick,
    ProviderAttempt,
    TwoGameRollout,
    WeeklyFeeObligation,
)
from src.services import two_game_fantasy, two_game_group
from src.services.weekly_fees import close_memberships, financial_lock
from tests.test_two_game_fantasy import fantasy as fantasy_fixture

fantasy = fantasy_fixture


async def fee_handoff(
    fantasy, monkeypatch, kind, change, *, identical=True, conflicting_body=False
):
    module = two_game_fantasy if kind == "fantasy" else two_game_group
    original_fees = module.materialize_entry_fees
    entered, release = asyncio.Event(), asyncio.Event()
    fee_calls = 0

    async def paused(*args, **kwargs):
        nonlocal fee_calls
        fee_calls += 1
        if fee_calls == 1:
            entered.set()
            await release.wait()
        return await original_fees(*args, **kwargs)

    monkeypatch.setattr(module, "materialize_entry_fees", paused)
    body = fantasy.body()
    path = fantasy.path + "/slots/1"
    game = fantasy.game
    if kind == "group":
        body.pop("odds")
        path = fantasy.path.replace("fantasy", "group") + "/pick"
        game = fantasy.group

    async def send(payload):
        return await fantasy.request("PUT", path=path, body=payload)

    waiting = asyncio.create_task(send(body))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        accepted_body = body if identical else {**body, "operation_id": str(uuid.uuid4())}
        if conflicting_body:
            accepted_body = {**body, "fixture_id": str(fantasy.fixtures[1].id)}
        accepted = await send(accepted_body)
        assert accepted.status_code == 200, accepted.text
        if change in {"locked", "left"}:
            fantasy.source.clock.now = game.locks_at
        if change == "off":
            monkeypatch.setattr(settings, "two_games_enabled", False)
        elif change in {"suspended", "left", "unpaid", "deleted"}:
            async with fantasy.sessions() as db, db.begin():
                await financial_lock(db, fantasy.league.id)
                if change == "suspended":
                    await db.execute(
                        update(TwoGameRollout)
                        .where(TwoGameRollout.league_id == fantasy.league.id)
                        .values(suspended=True)
                    )
                elif change == "left":
                    await close_memberships(
                        db,
                        [fantasy.league.id],
                        fantasy.source.clock.now,
                        player_id=fantasy.players[0].id,
                    )
                    await db.execute(
                        update(LeagueMembership)
                        .where(
                            LeagueMembership.league_id == fantasy.league.id,
                            LeagueMembership.player_id == fantasy.players[0].id,
                        )
                        .values(deleted_at=fantasy.source.clock.now)
                    )
                elif change == "deleted":
                    await db.execute(
                        update(League)
                        .where(League.id == fantasy.league.id)
                        .values(deleted_at=fantasy.source.clock.now)
                    )
                else:
                    db.add(
                        LedgerEntry(
                            league_id=fantasy.league.id,
                            player_id=fantasy.players[0].id,
                            kind=LedgerKind.adjustment,
                            amount_pence=-2000,
                            note="Synthetic concurrent balance correction",
                        )
                    )
        release.set()
        response = await waiting
        if conflicting_body:
            assert response.status_code == 409, response.text
            assert response.json()["detail"]["code"] == "OPERATION_CONFLICT"
        elif change == "deleted":
            assert response.status_code == 404, response.text
            assert response.json()["detail"]["code"] == "NOT_FOUND"
        elif identical:
            assert response.status_code == 200, response.text
            assert response.json() == accepted.json()
        else:
            assert response.status_code == 409, response.text
            assert response.json()["detail"]["code"] == "LOCKED"
        model = FantasyPick if kind == "fantasy" else GroupPick
        async with fantasy.sessions() as db:
            pick = await db.scalar(select(model).where(model.game_id == game.id))
            assert str(pick.operation_id) == accepted_body["operation_id"]
            assert pick.revision == 1
        assert fee_calls == 2
        assert await fantasy.count(model) == await fantasy.count(GameOperation) == 1
        assert await fantasy.count(WeeklyFeeObligation) == 1
        assert (
            len(fantasy.source.calls)
            == await fantasy.count(ProviderAttempt)
            == (1 if kind == "fantasy" else 0)
        )
    finally:
        release.set()
        await asyncio.gather(waiting, return_exceptions=True)


@pytest.mark.parametrize("kind", ["group", "fantasy"])
@pytest.mark.parametrize("change", ["locked", "suspended", "off", "left", "unpaid"])
@pytest.mark.asyncio
async def test_accepted_identical_operation_survives_late_fee_refusal(
    fantasy, monkeypatch, kind, change
):
    await fee_handoff(fantasy, monkeypatch, kind, change)


@pytest.mark.parametrize("kind", ["group", "fantasy"])
@pytest.mark.asyncio
async def test_other_accepted_operation_cannot_turn_late_refusal_into_success(
    fantasy, monkeypatch, kind
):
    await fee_handoff(fantasy, monkeypatch, kind, "locked", identical=False)


@pytest.mark.parametrize("kind", ["group", "fantasy"])
@pytest.mark.asyncio
async def test_late_replay_preserves_the_accepted_operation_body(fantasy, monkeypatch, kind):
    await fee_handoff(fantasy, monkeypatch, kind, "locked", conflicting_body=True)


@pytest.mark.parametrize("kind", ["group", "fantasy"])
@pytest.mark.asyncio
async def test_late_replay_does_not_bypass_deleted_league_scope(fantasy, monkeypatch, kind):
    await fee_handoff(fantasy, monkeypatch, kind, "deleted")


@pytest.mark.asyncio
async def test_accepted_fantasy_retry_precedes_action_refusal(fantasy, monkeypatch):
    original_fees = two_game_fantasy.materialize_entry_fees
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def paused(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return await original_fees(*args, **kwargs)

    monkeypatch.setattr(two_game_fantasy, "materialize_entry_fees", paused)
    body = fantasy.body()
    waiting = asyncio.create_task(fantasy.save(1, body))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        accepted = await fantasy.save(1, body)
        assert accepted.status_code == 200, accepted.text

        def refused(*args, **kwargs):
            raise HTTPException(429, detail={"code": "TOO_MANY_TRIES"})

        monkeypatch.setattr(two_game_fantasy, "admit_action", refused)
        release.set()
        response = await waiting
        assert response.status_code == 200, response.text
        assert response.json() == accepted.json()
        assert await fantasy.count(GameOperation) == await fantasy.count(FantasyPick) == 1
        assert await fantasy.count(WeeklyFeeObligation) == 1
        assert len(fantasy.source.calls) == await fantasy.count(ProviderAttempt) == 1
    finally:
        release.set()
        await asyncio.gather(waiting, return_exceptions=True)
