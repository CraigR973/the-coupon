# ADR 0007 — FotMob as the football-data provider

Status: **accepted, 2026-08-20.** Scoped as Batch 46. Supersedes ADR 0003's choice
of *provider*. Everything else ADR 0003 decided — the port, the ingestion
boundary, standings stored as published, and the alias layer — stands unchanged
and is the reason this is a small decision rather than a rebuild.

## Context

ADR 0003 chose API-Football on coverage, and coverage is why it has to be
replaced. Batch 16 built the feature against it in August 2026. It has never
stored a row: `teams`, `team_aliases`, `matches` and `standings` are empty in
every environment and always have been.

Three batches were spent finding out why, each uncovering a real defect that hid
the next one. Batch 28 found the undocumented 10-requests-a-minute ceiling.
Batch 33 found the null fields in the catalogue. Batch 45 found that a sweep
failing all 21 competitions logged `football data synced` and exited `0`, which
is what let the other two stay hidden for weeks and what made an empty `teams`
table read as a team-matching defect that did not exist.

The 2026-08-20 sweep, the first to get past all three, answered the real
question. **API-Football's Free plan carries no season after 2024.** Verified
live the same day with the sealed production key:

- `/standings`, `/fixtures` **and** `/teams` all refuse season 2026 with
  *"Free plans do not have access to this season, try from 2022 to 2024."* The
  refusal is plan-wide, not a missing table — every season-scoped endpoint is
  walled.
- Season **2025 is refused too**, so this is not "the new season has not been
  released yet". The most recent data the plan can reach is 2024/25, which ended
  2025-05-25.
- `/fixtures` with a date window and no season is rejected outright — *"The
  Season field is required"* — so there is no way round the gate.
- `/status` reports plan `Free`, active to 2027-07-24, and season 2024 returns a
  complete table. The key is valid and the adapter works. This is an entitlement
  wall, not a bug, and no amount of code fixes it.

Pinning `FOOTBALL_SEASON` to 2024 is not the workaround it appears to be: it
would render tables and form from two seasons ago against 2026/27 fixtures,
across divisions whose membership has changed twice since.

## The binding constraint is the bottom of the card, not the top

The card was measured from production on 2026-08-20 rather than assumed: **21
competitions, 416 fixtures.** Where the weight sits is the whole decision.

| Tier | Fixtures | Share |
| --- | --- | --- |
| English step 6–7 (National League North and South, Southern Premier Central and South, Northern Premier, Isthmian Premier) | 203 | 49% |
| Scottish Highland League, Northern Irish Premiership and Championship 1 | 63 | 15% |
| English and Scottish league pyramids, National League upward | 123 | 30% |
| Cups (no table to carry) | 27 | 6% |

The Premier League is three fixtures. A provider that serves the top of the game
and starves the rest fails this card by half, and that has now been the deciding
constraint three times — ADR 0002 for the Exchange, ADR 0003 for
football-data.org, and here.

## What was evaluated, and what each one actually does

Every figure below was probed live on 2026-08-20, not taken from documentation.

- **football-data.org** — free tier is exactly 12 competitions, confirmed
  unauthenticated against `/v4/competitions`, of which the British ones are the
  Premier League and the Championship. Its *entire* catalogue holds 16 British
  competitions and nothing below the National League at any price. ADR 0003's
  original judgement, re-confirmed.
- **openfootball** — genuinely maintained open data, but 2026-27 carries the
  Premier League and Championship only, and there is no Scotland repository.
- **TheSportsDB** — has the coverage, including Isthmian, Highland, the NIFL
  divisions and Cymru, all reporting the current season. The free tier truncates
  **every** table to five rows and **every** results feed to one event, including
  for finished seasons. It is a teaser, not a source. The paid tier at roughly
  $9/month clears the bar.
- **football-data.co.uk** — free, no key, no rate limit, and covers nine of the
  18 leagues. It publishes results only, never a table, which collides with the
  standings-as-published rule below. It is also unreachable from the development
  machine (TLS reset) while working normally from Railway.
- **Wikipedia** — around 91% of league fixtures, CC-licensed and legitimately
  reusable, with published tables that carry points deductions. Rejected on cost
  of parsing rather than coverage: HTML tables with no stability contract, and no
  current-season articles for Northern Ireland.
- **FotMob** — **17 of the 18 league competitions, 368 of the 389 league
  fixtures**, missing only `northern-ireland-championship-1`. The only free
  source found that reaches the English step 6–7 divisions that are half the
  card. (It also lists the EFL Cup and the Scottish League Cup, but a cup has no
  table under any provider, so the leagues are the honest measure.)

## Decision

Use **FotMob** as the football-data provider, as a third implementation behind
the unchanged `FootballDataProvider` port, selected by
`FOOTBALL_DATA_PROVIDER=fotmob`. `apifootball` stays selectable and stays
correct for anyone whose card fits its plan.

## One league id carries several of our competitions

This is the one shape the existing code has no answer for, and the main risk in
Batch 46.

API-Football is 1:1 — one competition resolves to one league id. FotMob is not:

- `8944` is National League North **and** National League South;
- `8947` is Southern Premier Central, Southern Premier South, Northern Premier
  **and** Isthmian Premier;
- `9545` is the Highland League with both Lowland divisions.

The port calls `fetch_table` once per `CompetitionKey`, so the obvious adapter
fetches `8947` four times for one payload. Memoise the league-id response for the
life of a run — the same device `ApiFootballProvider` already uses for its
catalogue — and those four competitions cost one upstream request between them.

The efficiency is the lesser half. Each returned group must be attributed to the
right `CompetitionKey` **before** any club is stored, because a Southern Central
side filed under Isthmian produces a wrong club inside a table that looks
entirely well-formed. `team_matching`'s fuzzy stage is scoped to a single
division precisely to make that impossible; a mis-attributed group hands it the
wrong scope and disables the guard. Exact-string matching against a provider's
own vocabulary has caused four defects in this project already, and combined ids
are a fifth way to make the same mistake.

## The results half, verified 2026-08-20

When this ADR was first written its coverage claim rested on **tables only** —
`8944`, `8947` and `9545` were confirmed to return full current-season
standings, and `fetch_results` was never checked. That was a real gap in a
document written as a settled decision: `fetch_results` is half the port, and
the form strip on the pick card is derived from `matches`, not from a table's
form string. It was closed by probing from Railway before Batch 46 was written.

**One request returns both halves.** `GET /api/data/leagues?id=<id>&season=<yyyy%2Fyyyy>`
carries `table` *and* `fixtures` in a single payload. This ADR previously assumed
api-football's shape of two requests per competition; it is one, and that makes
the whole batch cheaper than scoped — `8947`'s four competitions cost **one**
upstream request between them once memoised, for both tables and results.

**Tables split cleanly; results do not.** For a combined id the payload sets
`table[0].data.composite = true` and carries `data.tables`, one group per real
division, each with its own `leagueId` and `leagueName`:

| id | groups |
| --- | --- |
| `8944` | `940360` National League North, `940374` National League South |
| `8947` | `941117` Southern Premier Central, `941118` Southern Premier South, `941116` Northern Premier, `941109` Isthmian Premier |
| `117` (control) | `composite: false`, a single `data.table` |

`fixtures.allMatches` is a **flat list with no division identifier at all** —
its keys are `away`, `home`, `id`, `pageUrl`, `round`, `roundName`, `status`,
and `round`/`roundName` are matchweek numbers. `8944` returns 1104 matches
across two divisions with nothing on a match saying which.

**The resolution is an exact index, not name matching.** Table rows carry an
integer team `id`, so the group structure yields a team-id → division map — 48
entries for `8944` — and every match is attributed by its home team's id.
Measured on the live payload:

- 1104 / 1104 matches resolve to a division; 67 / 67 finished matches do too;
- 67 / 67 finished matches have **both** teams in the same division, so no
  cross-division fixture pollutes the mapping.

This matters because it keeps the correctness trap above closed by *identity*
rather than by string similarity. `team_matching`'s fuzzy stage is never asked
to decide which division a club belongs to.

**Scores parse straightforwardly.** A finished match carries
`status.scoreStr: "1 - 2"`, `status.finished: true`, `status.reason.short: "FT"`,
and `status.utcTime: "2026-08-08T14:00:00Z"` — already offset-carrying, which is
the shape Batch 43 established this codebase wants.

The consequence for Batch 46: `fetch_table` and `fetch_results` share one cached
payload per league id, and the adapter builds the team-id index once per id and
uses it for both.

## What does not change

ADR 0003's architecture survives intact, which is the point of having had a port
at all:

- **Nothing reaches a provider from the request path.** Ingestion writes
  `teams` / `matches` / `standings`; every screen reads those. FotMob publishes
  no quota, so the 100-a-day cliff is gone, but the rule is not a quota
  optimisation — it is what stops one member's refresh becoming an outbound
  dependency.
- **Standings are stored as published**, never computed. This is why
  football-data.co.uk cannot serve on its own, and it is a live requirement:
  points deductions and each competition's own ordering rules belong to the
  competition.
- **The alias layer is the seam**, now spanning three vocabularies rather than
  two. FotMob's spellings land as `source='provider'` rows beside the odds
  spellings, keyed `(competition_id, normalised)` exactly as before.
- `football_competitions_per_run` and `football_competition_spacing_seconds`
  **stay**. They are still right for `apifootball`. What changes is that pacing
  becomes the provider's to own, so a 12-second gap tuned to a 10-a-minute
  ceiling stops costing six minutes a run for a limit FotMob does not impose.

`FOOTBALL_API_KEY` is meaningless here, and the production validator must not
demand one for this provider.

## The terms of service

**FotMob's terms prohibit automated access.** This is recorded rather than
buried because it is an owner decision, taken knowingly on 2026-08-20, against a
usage profile of one sweep a day across 21 competitions. **Reaffirmed the same
day** when the owner instructed that Batch 46 be implemented after reading the
argument for deferring it.

Writing it down is the whole point. It keeps the decision revisitable, and it
means whoever next reads the adapter meets a dated judgement instead of
discovering an undisclosed dependency. If the position changes — theirs or ours
— TheSportsDB's paid tier is the identified fallback at roughly $9/month, and it
was measured against the same card so the swap does not need this search
repeating.

## The interface is undocumented, and it moves

Not a hypothetical risk. During the 2026-08-20 investigation,
`/api/leagues?id=47` — the path essentially every public wrapper uses — returned
`404`. The working path is `/api/data/allLeagues`. No version, no deprecation
window, no changelog: the interface had already moved, and the only signal was a
404 where data used to be.

Three things make that survivable, and they must all hold:

1. Read every field defensively, as ADR 0003 already required — unknown keys
   ignored, absent ones defaulted, an unreadable payload logged and dropped.
2. Treat a 404 on a known path as an **error**, never as "this competition has
   no table". The distinction between *absent* and *broken* is what the previous
   provider got wrong for weeks.
3. Keep Batch 45's verdict intact. A sweep that attempts a non-empty card and
   carries none of it fails and exits non-zero, so a path change surfaces as a
   red cron the next morning rather than as a table that quietly stops moving.
   Batch 45 shipped before this decision was taken, and it is what makes this
   dependency tolerable at all. It must not be weakened to accommodate a flaky
   source.

## Consequences

- **This costs no migration, and only because it is being done now.**
  `provider_team_id` is globally unique and two providers' ids would collide, but
  the four tables have never held a row. The same change after they are populated
  is an id-namespace migration and a materially larger batch.
- `northern-ireland-championship-1` resolves to nothing and its 21 fixtures
  render exactly as they did before Batch 16. Form is an enhancement, never a
  precondition for picking, so a competition with no table is a degraded card and
  not a broken one.
- The application now holds three vocabularies. The alias table absorbs it, and
  every link it makes stays one visible, correctable row.
- The dependency can break without notice. That is priced in above rather than
  wished away.
- Reverting is one variable. The adapter stays in the tree and `apifootball`
  stays selectable, so a change of plan is a config change, not a revert.
- **Probes must run from Railway, not from a laptop.** The development machine
  cannot reach several of these hosts — football-data.co.uk resets TLS from here
  and serves normally from production — so a local failure proves nothing about
  the deployment. Every measurement in this ADR was taken via `railway ssh`.
