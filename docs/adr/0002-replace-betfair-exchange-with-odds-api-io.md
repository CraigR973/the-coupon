# ADR 0002 — Replace the Betfair Exchange with odds-api.io, priced by Bet365

Status: **accepted, not implemented**, 2026-08-04. Scoped as Batch 7.

## Context

The application sources fixtures, prices, and settlement from the Betfair
Exchange. The Exchange does not price the lower British divisions, which the
owner requires. Verified on 2026-08-04 by four independent methods: the full
98-competition list held only `Scottish Premiership` and `Scottish
Championship`; competition ids 106 and 108-110 returned zero events; an
unfiltered sweep of every soccer event on 2026-08-08 found no Scottish
lower-league fixture; and a text search on twenty lower-league clubs across all
sports returned nothing.

The prices the owner could see are on the Betfair **Sportsbook**
(`betfair.com/betting/...`), a different product from the Exchange.
`SportsAPING` serves the Exchange only, so no configuration change reaches them.

`odds-api.io` aggregates 273 bookmakers, including both Bet365 and Betfair
Sportsbook, and carries the missing divisions.

## Decision

Replace the Betfair Exchange as the odds source with `odds-api.io`, pinned to a
single bookmaker. **Bet365 is the price basis**, chosen by the owner.

One bookmaker, not several. The game scores by odds, so mixing books — or
mixing a book with an exchange — would make a member's score depend on which
source priced their fixture rather than on the risk they took.

## Verified before deciding, 2026-08-04

- 727 football leagues. UK coverage is complete: all four Scottish divisions
  (`Scotland - Premiership`, `- Championship`, `- League One` with 61 events,
  `- League Two` with 55), England's full pyramid including `National League`
  and the amateur tiers, plus Wales and Northern Ireland.
- Free plan: £0, two bookmakers, 100 requests/hour and 500/day.
- For all five `Scotland - League One` fixtures on 2026-08-08, **Bet365 carries
  both `ML` and `Both Teams To Score`** — 5/5 on each. Betfair Sportsbook
  matches it. Bet365 additionally exposes handicap, corners, and totals markets
  the application does not use.
- Sample price, Airdrieonians v East Kilbride: `ML` home 4.75, draw 3.90, away
  1.67; `Both Teams To Score` yes 1.75, no 2.05.

Note the league naming is `Scotland - League One`, not `Scottish League One`.
An early probe reported these as missing purely because of that; exact-string
matching against a provider's own vocabulary has now caused three separate
defects in this project and must be treated as a hazard, not a detail.

## Scope

### The port is already narrow

Outside `apps/api/src/services/betfair.py`, only three adapter methods are used
anywhere: `fetch_slate`, `fetch_odds`, and `settle`. The `list_competitions` /
`list_events` / `list_market_catalogue` / `list_market_book` primitives are
Betfair's own RPC vocabulary and are internal.

Extract a provider-neutral port with those three domain methods plus the
`login` / `keep_alive` / `close` lifecycle. `Betfair`, `FakeBetfair`, and the
new provider all implement it. Rename `BetfairAdapter` to `OddsProvider` and
`BetfairDep` accordingly; `deps.py`, `betfair_session.py`, `scheduler.py`,
`services/gameweek.py`, `services/scoring.py`, `routers/gameweek.py`, and
`routers/picks.py` reference the old name.

### Provider implementation

- Slate: `GET /v3/events?sport=football&league=<slug>` per UK league slug, then
  the existing rule — Saturday 15:00 Europe/London, British only. Event dates
  are UTC with a `Z` suffix.
- Odds: `GET /v3/odds?eventId=<id>&bookmakers=Bet365`. Map `ML` →
  `MATCH_ODDS` with `home`/`draw`/`away`, and `Both Teams To Score` →
  `BOTH_TEAMS_TO_SCORE` with `yes`/`no`. Prices arrive as **strings** and must
  become `Decimal`, not `float`, to match `odds_at_pick`'s `Numeric(6, 2)`.
- Retain the existing rule that only priced selections are offerable.

### Settlement is the hard part

Betfair settlement reads runner status from Exchange market books. odds-api.io
exposes `status` and `scores: {home, away}` on the event instead, so settlement
must be derived: `MATCH_ODDS` from the score comparison, `BOTH_TEAMS_TO_SCORE`
from both scores being non-zero.

This must be proven before the batch closes, not assumed. Confirm that scores
populate, that `status` transitions to a terminal value, and how quickly after
full time — the scheduler settles at Saturday 22:00 with Sunday and Monday
retries, so a provider that lags beyond Monday breaks scoring. Also confirm
behaviour for a postponed or abandoned fixture, which the current
implementation handles as a `void` pick.

### Rate limits force a cache

500 requests/day and 100/hour. A slate refresh plus odds for roughly forty
fixtures is about forty-five calls, which is fine daily. But `fetch_odds` is
currently called **in the request path** — `routers/gameweek.py:132` and
`routers/picks.py:207` — so fifteen members loading the pick page repeatedly
would exhaust the daily quota.

Add a short-lived server-side cache for odds keyed by event, or refresh odds on
the scheduler and serve stored snapshots. This is a required part of the batch,
not a follow-up.

### Schema

Three columns carry the provider's name and will hold odds-api.io identifiers:
`fixtures.betfair_event_id`, `picks.betfair_market_id`, and
`picks.betfair_selection_id`. All are `NOT NULL`; the unique constraint
`uq_fixtures_gameweek_event` depends on the first.

odds-api.io has no per-selection identifier, so `picks.betfair_selection_id`
(`BigInteger`) has no natural value. Decide between widening the model to a
provider-neutral pair and dropping the unused column, or synthesising a stable
identifier. Either way this is a migration — revision `005` — and production
already holds a bootstrapped administrator, so it must be forward-only and
safe on populated tables.

### Configuration

- `ODDS_PROVIDER` selecting `oddsapi`, `betfair`, or `fake`, defaulting to
  `oddsapi`, with production rejecting `fake` exactly as it rejects
  `BF_FAKE_MODE` today.
- `ODDS_API_KEY` and `ODDS_API_BOOKMAKER`, the latter defaulting to `Bet365`.
- Retire or gate the `BF_*` variables. The Betfair certificate materialisation
  in `runtime_secrets.py` and its production file-permission validation become
  dead once the Exchange client is removed.

## Verification

- Unit tests against canned payloads captured from the real API, including the
  `Scotland - League One` shapes recorded above.
- A test proving a Bet365-priced Scottish lower-division fixture reaches the
  slate — the exact case the Exchange could not serve.
- Settlement tests for home win, away win, draw, both-teams-scored, clean
  sheet, and a postponed fixture.
- A rate-limit test proving repeated pick-page loads do not issue repeated
  upstream calls.
- The full existing gate: ruff, strict mypy, clean-PostgreSQL migrations
  through `005`, the API suite, frontend lint/typecheck/tests/build, the
  production-bundle Playwright flow, and the deployment-config assertions.
- A live coverage re-run of `.launch-private/weekend-fixtures.py` against the
  new provider, showing at least fifteen distinct priced selections for the
  intended launch Saturday.

## Verified during implementation, 2026-08-04

Against the live v3 API. Four of the assumptions above were wrong, and each one would
have shipped a broken game.

**Settlement does not come from the odds endpoints.** The scope above says the event
exposes `status` and `scores`, which is true — on `/events`. Once a fixture settles,
`/odds` returns it with `status: "settled"` but **no `scores` key and no bookmakers**,
and `/odds/multi` omits it from the response entirely; both carry only what is still
priced. Settlement reads `GET /v3/events/{id}`. There is no batch form — `/events`
ignores an `eventIds` filter and returns the whole book — so it is one request per
fixture still awaiting a result.

**Status is the gate, not the presence of a score.** A *pending* fixture already reports
`scores: {home: 0, away: 0}`, and a *live* one reports the score so far. Deriving
settlement from a score's presence would have resolved the entire slate as goalless
draws before kick-off, and paid out in-play matches at half time. The live vocabulary is
`pending` → `live` → `settled`, plus `cancelled`.

**Settlement timing is comfortable.** Sampling 227 football events: fixtures reach
`settled` from roughly **two hours** after kick-off (13 of 13 between 2-4h, 9 of 11
between 4-6h). A 15:00 kick-off settles well before the scheduler's first 18:00 Saturday
run, so the Sunday/Monday retries are slack rather than load-bearing. The ADR's worry
about a provider lagging past Monday does not arise.

**Leagues carry no `country` field, and England's lower tiers are qualified.** The
catalogue returns `{name, slug, eventsCount}` for 728 competitions, so the country is
only ever in the name. England's amateur tiers sit under `England Amateur - …` — the same
pattern Austria, Denmark, Germany, Sweden and Turkiye use — and reading the whole prefix
as the country silently drops eight competitions including National League North and
South. Matching must also stay exact after normalisation: `Ukraine` begins with `uk`.

Two smaller corrections: event `id` is a JSON **number** and `league` a nested
`{name, slug}` object, so both need coercion; and `/odds/multi` rejects more than **ten**
event ids per request.

**Coverage, for the intended launch Saturday 2026-08-08:** 30 UK leagues, **131**
qualifying 15:00 fixtures, 56 of them priced by Bet365, giving **280 distinct priced
selections** against the 15 a full league needs. All five `Scotland - League One` and all
five `Scotland - League Two` fixtures carry both markets — the coverage the Exchange
never had.

**Consequence for the rate limit.** 131 fixtures batched ten at a time is 14 requests per
full odds refresh, so `ODDS_CACHE_TTL_SECONDS` defaults to 900 rather than 300: at 300s
the pick page would cost 168 requests/hour against a 100/hour plan. The 500/day cap is
the tighter constraint under sustained match-day refreshing and is the first thing to
raise if the provider starts returning 429s.

## Consequences

- The module docstring's premise — that Betfair was chosen for Scottish
  lower-division pricing — is inverted and must be rewritten.
- `docs/LAUNCH_PLAN.md` platform notes citing Betfair certificate login and the
  delayed key stop applying once the Exchange client is removed.
- L4's Betfair probe evidence and the `BF_*` sealed variables become historical.
  L4 should close on its own terms first; this batch then supersedes part of it.
- Prices become Bet365's, which carry a bookmaker's margin. Exchange prices ran
  higher, so scores computed after this change are not comparable with any
  computed before it. Irrelevant before launch; material afterwards.
- The free plan pins two bookmakers and changing the selection requires a `PUT`.
  Bet365 must be one of them.

## Sequencing

`/batch-start 7` requires a clean worktree on `main`. The current tree holds the
uncommitted L4 branch, so L4 must be closed out first.

The three Betfair defects fixed on 2026-08-04 — certificate login field names,
sponsored English competition names, and the country-based slate rule — stay
valuable regardless. They are what makes the Exchange usable as a fallback and
they keep production working until this batch lands.
