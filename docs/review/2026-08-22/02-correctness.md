# 02 — Correctness

The game rules, the races around them, input handling, and time. Reviewed at
`308bc16` against a running `tests.e2e_server` on real PostgreSQL.

## CORR-01 · MED · Two endpoints answer 500 to a malformed UUID — **verified**

`routers/picks.py:58` types the submit body's `fixture_id` as `str`, and
`routers/picks.py:174` types the `gameweek_id` path parameter as `str`. Both are
handed straight to SQLAlchemy against a `UUID(as_uuid=True)` column, which raises
before any handler sees it.

Reproduced over HTTP:

    POST /api/v1/leagues/the-coupon/picks {"fixture_id":"not-a-uuid",...}   -> 500
    GET  /api/v1/leagues/the-coupon/gameweeks/not-a-uuid/pick               -> 500
    POST /api/v1/leagues/the-coupon/picks {"fixture_id":"<absent uuid>"}    -> 404  (correct)

So the type coercion is the whole of it — a well-formed id that does not exist is
already handled properly.

This is the codebase's own convention being missed in one file rather than a
pattern it lacks: `routers/players.py:83-87` does exactly the right thing —

    try:
        target = uuid.UUID(player_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Player not found")

— and every other router types its ids `uuid.UUID` and lets FastAPI answer 422.
`picks.py` is the only file with the gap. It matters because a 500 is the signal
you want reserved for a genuine fault; spending it on a stale link trains you to
ignore the alert that means something.

## CORR-02 · MED · The lock is checked before the provider call, not after

`routers/picks.py:115` evaluates `pick_refusal(gameweek, _now())`, then line 127
makes an outbound HTTP call to the odds provider, then line 150 commits. Nothing
re-checks the deadline between the second and the third.

The window is exactly as long as `fetch_odds` takes. That is normally
milliseconds, but it is a network call to a third party on the request path with
no timeout budget stated at the call site, and this is the one deadline the whole
product is built around: a pick that lands at 14:30:03 scores like any other.

`pick_refusal` is time-authoritative rather than status-authoritative — deliberate
and correct, per its docstring — which means the fix is cheap: re-evaluate it
against the same `now` after the snapshot returns and before the commit, or push
the deadline into the write as a conditional.

## CORR-03 · MED · A pick can outspend the provider's hourly budget

`config.py:92-119` reasons carefully about the browse path and concludes the
tightest hour is 28 requests against a 100/hour allowance. The *pick* path is
priced separately, at "1 request per fixture" with a 60-second cache
(`odds_cache_pick_ttl_seconds`).

But `submit_pick` is rate-limited at `60/hour` per user (`picks.py:101`). A
member who changes their mind across 60 different fixtures in an hour spends 60
provider requests, because the 60-second cache only helps for repeats of the
*same* fixture. Two such members exceed the 100/hour allowance on their own,
before the browse path or the discovery job has spent anything.

This is a real-Saturday shape, not a contrived one: deciding between fixtures is
what the hour before lock is for. The per-user limit and the provider budget were
each set sensibly and were never multiplied together.

## CORR-04 · LOW · Changing `pick_scope` mid-round leaves the fixture rule unenforced

`models/pick.py:59-62` explains that `uq_picks_league_gameweek_fixture` is a
*partial* unique index predicated on `pick_scope`, denormalised onto each row
because an index predicate cannot join to `leagues`. `_apply_selection`
(`picks.py:344`) copies the league's current scope onto the row at write time.

So rows written under `selection` carry `pick_scope='selection'` and are outside
the partial index forever. If a league switches to `fixture` scope while a round
is open, the picks already taken do not contend with the new ones, and two
members can end the round holding the same game under a rule that forbids it.

Whether this is reachable depends on whether league settings permit a scope
change on an open round — worth confirming before deciding it needs a fix.

## CORR-05 · LOW · Non-existent and ambiguous local times at the DST boundary

`services/odds_provider.py:264-273` builds local instants as
`datetime(y, m, d, tzinfo=UK_TZ) + timedelta(minutes=...)`.

This is **correct** under `zoneinfo`, and worth saying plainly because the same
line under `pytz` would be a bug: `zoneinfo` resolves the offset from the
wall-clock time at access, so adding 900 minutes to local midnight yields 15:00
at whatever offset actually applies that day. The season spans BST and GMT and
the arithmetic holds across both.

The residue is only at the transition itself. A league whose window or lock lands
in 01:00–02:00 on the last Sunday of March asks for a wall time that does not
exist, and `fold=0` resolves it to the pre-transition offset rather than raising;
the October Sunday makes the same hour ambiguous. No league configuration in play
gets near it, and the default 15:00 window never can.

## Verified correct

- **Both uniqueness directions hold.** One pick per member per round and no two
  members on one claim are database constraints, not application checks, and
  `submit_pick` treats `IntegrityError` as the authority rather than trusting its
  own pre-check (`picks.py:149-155`).
- **The frozen price is server-side.** The client posts a fixture, market and
  outcome; the endpoint fetches and freezes the price itself, and refuses an
  outcome the provider is not currently offering rather than storing a stale one.
- **A missing provider refuses the pick loudly** (503, `ODDS_UNAVAILABLE`) instead
  of degrading, which is right here even though the browse path degrades — the
  reasoning is written out at `picks.py:256-262` and I agree with it.
- **Naive-UTC storage is applied consistently**, and Batch 43 already fixed the
  offset-stamping bug that made a 14:30 London lock render as 13:30.
- **660 backend tests pass against real PostgreSQL**, including the pick flow,
  settlement, scheduler jobs and all four migration tests.
