# ADR 0003 — API-Football as the football-data provider

Status: **accepted and implemented**, 2026-08-06. Scoped as Batch 16.

## Context

Batch 16 shows real league tables, previous results, and recent form. None of
that can come from the existing source. `odds-api.io` prices fixtures and
publishes nothing else — no table, no historical result, no form — so a second
provider is required, and it is the first time this application has held two.

Our own data cannot substitute. The slate has only ever stored Saturday 15:00
kick-offs, so Sunday, Monday and midweek matches have never existed in this
database, and a table built from a third of a season's fixtures would be wrong
rather than incomplete. Scores were not persisted at all: `settle_gameweek`
reads a result from the odds provider, writes pick status and points, and keeps
nothing. There is also no `Team` table — `fixtures.home` / `away` are free text.

## Decision

Use **API-Football (api-sports.io)**, v3, as a second and independent provider
behind its own port, for tables and results only. The odds provider is unchanged
and remains the source of fixtures, prices, and settlement.

Coverage is the binding constraint, exactly as it was in ADR 0002. The slate is
the whole British card — all four Scottish divisions, England's pyramid through
the National Leagues, Wales and Northern Ireland. The obvious alternative,
`football-data.org`, carries twelve competitions on its free tier and none of
the lower British divisions. Choosing it would have reproduced the Betfair
failure precisely: a provider that serves the top of the game and starves the
rest of the slate.

## The constraints that shape everything: 100 requests a day, 10 a minute

The free plan allows **100 requests per day** and **10 requests per minute**.
The daily ceiling is a fifth of odds-api.io's 500; the minute ceiling means a
successful sweep still has to be paced rather than fired in one burst.

**Nothing may reach a provider from the request path.** Ingestion runs on the
scheduler and writes `teams` / `matches` / `standings`; every screen, inline or
standalone, reads those tables. This is not an optimisation applied afterwards:
putting `fetch_odds` in the request path is what forced the entire caching
apparatus in `services/odds_cache.py`, and here a single member pulling to
refresh could exhaust the day before lunch. `tests/test_football_router.py`
pins it by booby-trapping the shared session and asserting both endpoints still
answer.

The arithmetic, for the 30 UK competitions the slate carries: one catalogue
request per run (memoised on the client), then one `/standings` and one
`/fixtures` per competition — 61 for a full daily sweep, against 100.
`FOOTBALL_COMPETITIONS_PER_RUN` caps a run, and
`FOOTBALL_COMPETITION_SPACING_SECONDS` spaces competition attempts. The default
12-second gap keeps the two-request competition unit below 10/minute, so a
30-competition sweep takes about six minutes. Competitions are synced
least-recently-first so a slate that outgrows the cap rotates rather than
starving its tail.

A season backfill is a separate, deliberate, one-off run
(`python -m src.run_scheduled football-backfill`) rather than a scheduled job.
It is unbounded in date, so putting it on a clock would spend the daily
allowance re-fetching history that cannot change.

## Name reconciliation is a first-class layer, not a detail

`fixtures.home` / `away` come from odds-api.io and `teams.name` from
API-Football, and nothing joins them. "Airdrieonians FC" and "Airdrieonians" are
the same club; "Nott'm Forest" and "Nottingham Forest" are the same club; a
string comparison says otherwise. Exact-string matching against a provider's own
vocabulary has now caused **four** defects in this project — Betfair's certlogin
field names, its sponsored English competition names, a division allow-list that
starved the slate, and odds-api.io's `England Amateur -` country prefix.

`services/team_matching.py` is therefore three stages, cheapest first: an alias
lookup keyed `(competition_id, normalised)`; normalised equality; then
similarity scoped to one division and accepted only when it clears a threshold
*and* beats the runner-up by a margin. An ambiguous name resolves to **nothing**
— no form line is much better than another club's form line. Every resolution is
written back as an alias, so the layer gets cheaper and more accurate as it runs
and every link it has made is one visible, correctable row.

Aliases are learned at ingestion time, not read time, which is what keeps the
pick screen's inline form a primary-key lookup.

## Standings are stored as published, not computed

A table is not a sum of results. Points deductions, expunged records, and each
competition's own ordering rules — head-to-head in Scotland, goal difference in
England — belong to the competition, and reproducing them from scores would
produce a table that quietly disagrees with the official one.

## Configuration defaults to off

`FOOTBALL_DATA_PROVIDER` selects `apifootball`, `fake`, or `none`, and **`none`
is the default**. Production is already deployed and sealed; defaulting to a
provider whose key it does not hold would stop it starting. `none` disables
*ingestion* only — the screens still read whatever is stored, so an unconfigured
deployment shows no football rather than failing. `fake` is rejected in
production exactly as `ODDS_PROVIDER=fake` is.

## Verified during implementation, 2026-08-06

**The adapter was written against the documented v3 shapes and has not been run
against the live API from this machine.** Outbound requests to sports APIs are
blocked here, so the live probe is the owner's, as it was for odds-api.io —
where three live-only shape surprises were found, each of which would have taken
the batch down alone. Every field is therefore read defensively: unknown keys
ignored, absent ones defaulted, an unreadable payload logged and dropped rather
than raised.

Two documented shapes are already known to be traps and are covered by
`tests/test_api_football.py`:

- **Failures arrive with HTTP 200** and an `errors` object, so a quota
  exhaustion must not read as "this competition has no table". The minute-limit
  key is `rateLimit`, and is retried with the same backoff path as HTTP 429/5xx.
- **`standings` is a list *of lists*** — one inner list per group.

Status is the gate rather than the presence of a score, for the same reason it
is on the odds side: a not-started fixture carries a null score and an in-play
one carries a partial score, so `FT`/`AET`/`PEN` is what makes a result final.
An unknown status code leaves a match pending rather than recording a half-time
score.

One defect was found and fixed in this batch's own code: `standings.updated_at`
had no `onupdate` and no trigger, so it froze at insert. That broke the "as of"
line, and — more seriously — froze the least-recently-synced ordering, which
would have left every competition past the per-run cap never resynced after its
first pass. It is now stamped explicitly in `sync_table`; a server-side `NOW()`
would not do, because it is the transaction's start time and a run syncing
several competitions would give them all one indistinguishable timestamp.

## Consequences

- The application now holds two providers with different vocabularies, and the
  alias table is the seam between them. A wrong link is a visible row, fixable
  without a deploy.
- `matches` is a **separate** record from `fixtures`, not an extension of it. A
  fixture is something a league can pick on; a match is something that happened.
  Most matches are neither pickable nor picked. They are related through
  `team_aliases` and kick-off, deliberately not by a foreign key: the providers'
  event ids share no namespace, and a fixture postponed out of its window still
  has a match row when it is eventually played.
- A season is named by its starting year (2026-27 is `2026`), rolling over in
  July. `FOOTBALL_SEASON` overrides it, which is what a backfill of a finished
  season needs.
- Fixtures whose clubs do not resolve simply have no context, and the pick screen
  renders exactly as it did before this batch. Form is an enhancement, never a
  precondition for picking.
- The owner must run a live probe before this is useful in production, and set
  `FOOTBALL_DATA_PROVIDER` and `FOOTBALL_API_KEY`. Until then the deployment is
  unchanged.
