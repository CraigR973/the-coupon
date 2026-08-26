# Status — The Coupon

## Now

A full-application review landed on 2026-08-22 (`docs/review/2026-08-22/`),
covering engineering, security, UI/UX, accessibility, dependencies and
operations against a running instance rather than the source alone. It found 24
things and specified Batches 54-60 from them. The baseline it measured: **1,047
tests green** — 660 backend against real PostgreSQL, 387 frontend — with ruff,
mypy, eslint and tsc clean, and production serving every security header it
should while `/api/docs` correctly 404s.

Batch 54 closed the first of them. `--text-muted` had been contrast-checked
against two of the four surface tiers and shipped, so it failed wherever a card
sits on a card — which is where the pick screen puts every "WIN n PTS" line. The
light palette had never had the pass the dark one got and failed against every
light surface. Measured live with axe: dark went 7 failing nodes to 0, light 21
to 6. The six that remain are `--primary` and `--warning` used as text, and they
are arithmetic rather than oversight: no single value clears 4.5:1 both as text
on white and as a fill under near-black. They need a second token, which is a
design decision and is left for the owner.

Batch 55 gave members back pinch-zoom. `index.html` had shipped
`maximum-scale=1.0, user-scalable=no` — the only axe violation on every screen,
rated critical, and a WCAG 1.4.4 failure that falls hardest on the people
reading two-decimal odds at 10px. The reason that attribute usually exists is
now handled where it belongs: three Settings controls that rendered at 14px
were raised to 16px on mobile, so iOS Safari has no cause to zoom a focused
field. The form disclosure went from 70x22 to 70x24, clearing WCAG 2.2 SC
2.5.8. The pick screen now reports **zero** axe violations in both themes.

Batch 56 closed the account-recovery journey. Changing a PIN now revokes every
refresh token for that member — it previously wrote the new hash and left every
old session renewing itself for thirty days, so a stolen session outlived the
credential it was opened with. An expired lockout now returns all five attempts
rather than one, ending a ratchet that could lock a forgetful member out
permanently. And `pin/reset-request`, which promised "an admin will be notified"
and notified nobody, now writes an audit row *and* pushes every active site
admin. **This is the first backend change since the review, so a `/ship-prod` is
owed** — it is not live until then.

Batch 57 cleaned up the pick path. A malformed `fixture_id` or `gameweek_id`
answered **500**; both are now 404 and 422, with a well-formed-but-absent id
still 404. The lock is re-checked after the odds fetch returns, closing a window
as long as a third party takes to answer on the one deadline the product turns
on. And the per-member submit limit, which permitted one member to spend sixty
provider requests an hour against roughly twelve spare, is now a named
`PICK_SUBMIT_LIMIT` of `10/hour` asserted against the measured budget. The
aggregate is still unbounded — fifteen members at ten each exceeds the plan —
and that gap is stated in a test rather than left to be rediscovered.

Batch 58 made the rate limits real. `X-Forwarded-For` was read from the left —
the half a caller writes — so every IP-keyed limit in the app was bypassable by
rotating the header. It is now counted from the right by `trusted_proxy_count`,
verified live: seven logins with a rotating spoofed prefix hit 429 at the sixth
where each previously bought a fresh bucket. Replaying a rotated refresh token
now revokes every session for that member rather than letting victim and thief
race. `X-Correlation-ID` is accepted only as a UUID, `refresh_tokens` is pruned
nightly instead of growing forever, common PINs are refused, and every response
carries `Cache-Control: no-store`.

Batch 59 raised `cryptography` to 48.0.1. The old `<=46.0.3` bound rested on the
premise that the library never sees untrusted input, and that was wrong:
`push/subscribe` stores a browser-supplied `p256dh` which `webpush()` parses as
an EC public key, which is exactly the surface of the missing subgroup-validation
advisory. 48.0.1 clears everything reachable and is the last release with a macOS
universal2 wheel, so the local gate still builds without Rust. **The
FastAPI/starlette upgrade was built, measured and deliberately not landed** — it
passes 684 of 687, and the three failures are decisions rather than fixes (a
401/403 contract change the web client reacts to, and a datetime guard that goes
silent under pydantic 2.13). It is specified as Batch 61.

Batch 60 found that the one-command gate it was written to build already existed.
`scripts/ci-local.sh` runs ten checks — a venv from the pins, a clean `pgserver`,
`alembic upgrade head`, the **complete** pytest suite, deployment-config
assertions and the whole frontend — and passes. Nothing pointed at it: `AGENTS.md`
and `batch-verify.md` documented a piecemeal path that skips 151 tests without
`DATABASE_URL` and a borrowed venv that cannot even import the suite. All three
command docs now say so, and `phase-closeout.md` states plainly that its push
deploys the web app before CI has necessarily reported.

Batch 62 finished the palette. The six contrast failures Batch 54 left behind were
not a design decision after all: Tailwind scales colours per utility, so every
`text-*` now resolves to a new `-ink` token while every fill, border and ring keeps
the original. Nothing visual moved except small brand-coloured text in light mode,
which was the thing that was wrong. **The pick screen now reports zero axe
violations of any rule, in both themes** — it began the night with one critical and
21 contrast failures.

Batch 63 gave the product a way to make an account. There had never been one — not
in the API and not in the UI — so sharing the app's URL sent the recipient to a
sign-in form asking for a display name and PIN they could never obtain, and the
`/join/:token` invite link told them to ask their admin for credentials no flow
could issue. `POST /auth/register` is now unauthenticated: no invite, no join
code, returning the same token pair login returns so the caller lands signed in.
It creates an **account only** and joins no league, because the join code already
gates membership. This reverses part of L0's private-provisioning posture on the
owner's 2026-08-22 decision, recorded as ADR 0008 and superseding the
never-implemented ADR 0001. Since `display_name` is globally unique, is the login
identifier, and has no email behind it, the guards are the feature rather than
refinements to it: `5/hour` on the proxy-aware client address,
`PUBLIC_SIGNUP_ENABLED` as a kill switch needing no deploy, case-insensitive
uniqueness that **includes soft-deleted rows**, and a charset the login form can
reproduce. **The API half shipped on 2026-08-22 in `82a7a12`, closing what was the
first batch where that gap was user-visible** — Vercel deploys the web app from
`main` on push, so production carries a "Create account" button with no endpoint
behind it until then. Two consequences are left as owner decisions: the kill
switch closes the API but not the UI (gating the links needs `GET /api/v1/config`
made unauthenticated, reversing a documented decision), and a `public_open`
league — the `test` league is one — is now reachable by anyone with an account
rather than only by provisioned members.

Three member-reported bugs closed on 2026-08-22 (73245a7), outside the batch
sequence. The first was not a defect: every league is on `pick_scope = 'selection'`,
where a claim takes one outcome and the rest of the game stays open — so "someone
took Everton, I could still take the draw" was the configured rule. The owner wants
one member per game, which is a **settings** change, and the fix here is the bug that
switching would have exposed. The slate marked *every* selection on a game the caller
holds as `mine`; a client greys out anything already taken, so the whole game went
dead and the one member entitled to move between its markets could not, while the
"my pick" banner named whichever selection was priced first. `_selection_options` now
blocks only on a holder who is somebody else, matching `_claim_conflict`, with the
exact holder of a selection outranking the fixture-level blocker — which matters
because a league switched from `selection` to `fixture` keeps picks written under the
old rule and can genuinely have several holders on one game. **`zoe` cannot take the
switch yet**: two members hold Everton v Crystal Palace on the 2026-08-22 round and
`_apply_pick_scope_change` refuses that with `PICK_SCOPE_CONFLICT`. The other four
leagues would take it today, and the API has to ship before any of them do.

The second: both join paths navigated to the new league without dropping the cached
`['leagues', 'mine']` list, and every coupon surface gates its query on the
`hasLeagues` derived from it — so a new member landed on "You're not in a league yet",
the one screen they had joined to get past, for up to a minute. The third: the pyramid
ordering lived privately inside `CouponPickPage`, so Football Stats listed the same
divisions in the ingestion job's order; it is now `lib/competitions`, shared by both.

Batch 64 stopped the card offering games nobody was playing. On the first live
Saturday odds-api.io served the whole Scottish Premiership round as `pending`
while the matches were postponed or already moved to 15 September, and Bet365 was
still quoting prices on every one — so Rangers v St Mirren, St Johnstone v Celtic,
Hibernian v Kilmarnock, Motherwell v Aberdeen and Falkirk v Hearts all reached
members' cards and a Motherwell pick had to be returned by hand. Batch 49's
removal path was never going to fire: it waits for the odds provider to call a
fixture void and that provider did not know. `verify_slate` now takes a second
opinion from FotMob — already in production, no key — once per shared fetch, and
marks confirmed-off fixtures with a word already in `VOID_STATUSES` so the existing
link filter and `_drop_voided_fixtures` do the rest, picks returned and notified.
**A fixture is off when `status.cancelled` is true *or* it is not listed on the
day**; date alone is what let the two most visible games through a first attempt,
because FotMob keeps a postponed match's original kick-off. Every uncertainty
**fails open** — an unresolvable competition, an unmatched pair of names, a failed
request — since deleting a real fixture off a live card is worse than the phantom
it prevents. Against the live 137-fixture card it marked 8 off, all 8 already
removed by hand, and condemned nothing that was on. **The gap it does not close:**
FotMob carries neither NI Championship 1 nor the English non-league tiers, so those
fail open every week, and because `sync_slate` only ever adds links and `fixtures`
has no status column, a hand-removal there is undone by the next `refresh-slate`.

Batch 65 stopped the leagues jumping a week at 14:30 on Saturday. Members
reported them going "straight to the next week as soon as the picks are locked",
and there were **two independent causes**. `current_round_order` ranked a round
top only while it was accepting picks; discovery writes next week's round a
`slate_horizon_weeks` horizon ahead with `picks_open_at_utc` NULL, which counts
as claimable the instant the row exists, so from Sunday onwards both rounds sat
in the top tier and only the soonest-lock tiebreak kept this week in front — and
at the lock that tiebreak stopped applying, mid-afternoon, with the league's own
games still being played. A new top tier holds the round that has **locked and
not yet settled**, so the week now turns on the results rather than the deadline.
It is bounded: 48 hours past the close of the league's own window, which is six
consecutive 18:00/20:00/22:00 settlement sweeps, so a round the provider never
resolves — Batch 64's phantom Premiership round is that shape — cannot pin its
league forever. The window's close is read **per league**, so a Friday-to-Monday
round is still in play on Monday night. The second cause was the settings: a
window edit changed nothing about any round already discovered, which over the
horizon was every round a member could see, so an announced opening appeared to
do nothing for weeks. An edit now restamps both ends of the claim period on every
round that has **not locked** — the forward-only rule Batch 40 declined to
replace, kept exactly where it is load-bearing: a locked round keeps the deadline
its members claimed against. **API-side only, so it is not live until a
`/ship-prod` runs.**

Batch 66 gave a forgotten PIN a way back. Batch 56 made `pin/reset-request`
truthful — it writes an audit row and pushes every active site admin — and **the
action behind that notification did not exist**: the push sent the admin to their
own settings page because there was nowhere else to send them, and exactly one
endpoint in the API used the `AdminUser` dependency. The people half of the admin
console now exists — Players, Invites, All Leagues, behind `/api/v1/admin` and an
`/admin` route group gated on `role === 'admin'` — and the push lands on the
member it names. **An admin reset clears the credential rather than minting a
temporary PIN** (owner's decision): no secret passes through the admin, nothing
interim can be shared or reused, and the member chooses their own at `/set-pin`
where the existing charset rules apply. A cleared PIN is the *absence* of one —
login refuses it outright with `PIN_NOT_SET` — and the cleared state is claimable
only for 24 hours, read from the audit row the reset already writes rather than
from a column of its own. Both admin surfaces now share one implementation: the
league-admin reset predated Batch 56's revoke rule and never obeyed it, minting a
readable four-digit PIN and leaving every old session renewing itself for thirty
days. Player deletes are soft, so past leaderboards read as they were played, and
the display name stays reserved. **This is the only batch of the post-launch run
that adds an Alembic revision** — 016 drops `NOT NULL` from `profiles.pin_hash` —
so the `/ship-prod` carrying it wants a written forward recovery plan first.
**API-side as well as web, so it is not live until that ship runs.**

Batch 67 made a played round show its result. `CombinedAccaView` carried a
won/lost badge per leg and an "All legs won" line, which is the *outcome* and not
the result — the member wants the scoreline, and between one round ending and the
next opening this screen is where the week is read back. **The scoreline was not
in the product at all:** `fixtures` carries the teams, the kick-off and the
competition and no goals of any kind, and the odds provider settles in market and
outcome terms, so a won leg knew it had won and not by what. Scores live on
`matches`, keyed by `teams` rather than by the fixture's free-text names, so a leg
reaches one only through the name-based join Batch 64 built for the FotMob
cross-check — `PAIR_THRESHOLD` and `pair_score` have moved into `team_matching`
where the rest of the name work lives, and both callers now share them. **A wrong
join would print a false scoreline against a real member's pick**, so it fails to
*no score shown* rather than to a guess: both ends of the fixture must clear the
threshold independently, the date chooses between candidates rather than the name
score, and two candidates the date cannot separate resolve to nothing. **The link
is resolved per read rather than persisted** — the batch's one open design
decision — because a stored link goes stale when an alias is corrected, and the
alias layer is the part most likely to need correcting. Settled rounds only; live
scores are Batch 72. Each leg also carries what it scored and the reader's own leg
is marked, so how the week went and how I did are one glance. **API-side as well
as web, so the scorelines are not live until a `/ship-prod` runs** — every new
field is optional with a default, so the screen degrades rather than breaks in the
gap.

Batch 69 built the operational half of the admin console. Dashboard, Sync and
Results, and the value is measurable in work already done by hand: Batch 64
opened with a Motherwell pick returned manually and twelve fixtures removed
manually, and Batch 68 is a backfill run straight against the database. **A
manual trigger runs the coroutine the scheduler runs**, taken from the same
registry an external cron uses, so there is no second implementation to drift.
**A trigger that spends the odds provider's budget says what it costs before it
is pressed** — roughly 100 requests an hour across the whole deployment, shared
with the scheduler's own jobs, and exhaustion is silent — and draws on the very
same per-admin bucket the ad-hoc slate fetch uses rather than a second one beside
it. The bucket counts *slate walks*, so discovery, which walks the whole horizon,
is charged twice. Results takes a **scoreline** rather than a set of market
verdicts and feeds it into the existing `settle_gameweek` unchanged, so a
hand-entered result and a provider-supplied one write identical `picks` rows; a
round that has already settled refuses a second settlement, because this corrects
a round that is stuck rather than rewriting a week members have seen. **The
durable fixture status is deliberately not here** — `fixtures` has no status
column, so it needs a migration, and the row says to split that out. **API-side
as well as web, so it is not live until a `/ship-prod` runs.**

Batch 70 put the shape of a member's picks on the screens that already rank them.
Cumulative and average odds on the league table and the profile, plus the figures
that separate two members on the same points: points per pick played, best single
return, win rate and a favourite/longshot split at 3.00. **One change rather than
several** — `Standing` is the single ranking rule in the codebase and the
leaderboard, the profile and the cross-league summary all read it, so the figures
went into the aggregate once and every surface got them, including the two the
owner did not ask about. The profile's own win-rate computation went with it: it
divided the same two numbers the row already carried, which is how a profile and
a leaderboard end up a rounding step apart. **Void picks are the decision:**
`picks_played` counts them because a member whose fixture was postponed took part
in that round, and the odds figures do not, because a bet that never ran is not a
price to credit them with — so the two denominators genuinely differ, and a note
saying so ships *with* the figures on every surface and disappears when they
agree. Longest streak is deliberately absent: it needs ordered history rather than
an aggregate. **API-side as well as web, so the figures are not live until a
`/ship-prod` runs** — every field is additive with a default, so the table
degrades rather than breaks in the gap.

Batch 71 fixed two independent defects on Football Stats. The screen now opens
**collapsed** — one open division out of thirty was the right instinct with the
wrong answer, since the reader has not asked for any of them yet. The results half
was diagnosed before it was fixed, read-only against production on 2026-08-23,
because Batch 45 is the reason to check rather than assume: **ingestion is
healthy** — 567 finished matches across 18 competitions, all inside the 30-day
lookback — and **the read cap was the defect**. Saturday 2026-08-22 held 145
finished matches across 17 competitions, and the flat 20-row limit returned twenty
rows covering **six** of them; eleven divisions fell off the end of a global row
count, which is exactly the "partially there" that was reported. A flat count is
the wrong *shape* as well as the wrong number, because the screen groups by day
and then by competition: `/football/results` now returns every match on the three
most recent days that have results — days, not calendar days, so a Wednesday still
answers with the weekend — behind a row backstop that exists only to bound a
pathological ingestion. Measured against the same production data: **150 rows, all
17 competitions**. **API-side as well as web, so the fuller results are not live
until a `/ship-prod` runs**; the collapse fix is frontend-only and lands on merge.

Batch 72 put the score on the screen while the round is being played — the last of
the post-launch list and the only enhancement on it. It is affordable because the
source is already here: FotMob ships in production for tables, results and form,
**needs no key and has no rate limit to protect**, and Batch 67 had already built
the join a live score is read through. **It is display only and never touches
settlement:** the odds provider settles picks, and a second source moving
`Pick.status` would be two authorities on one fact — a member watching points
awarded and then withdrawn. The poll writes to `teams` and `matches` and nothing
else, and a test snapshots every pick row around a poll to prove it. **Polling
lives on the scheduler, every ten minutes, bounded to leagues with a round
actually in play** — Batch 65's own predicate, so a quiet Tuesday reads the
database and returns without a request, and a round the provider never settles
stops being polled once it passes the grace measured from its own window closing.
A running score stores with `finished=False`, which keeps it out of the results
screen, the form line and the settled scorelines, all three of which gate on it;
a competition FotMob does not carry renders the round without scores rather than
erroring. The leg says which kind of score it is and the screen says so in words,
because 2-1 at half time and 2-1 at full time are opposite news to somebody
holding that pick. **API-side as well as web, so live scores are not live until a
`/ship-prod` runs.**

Batch 68 wrote in the two rounds the league played before the product existed.
2-1 Hibs played on 8 and 15 August 2026 and The Coupon's first stored round is
22 August, which was also missing two members' picks. The owner supplied both
bet365 slips and both coupons on 2026-08-24, which is what unblocked it: **the
odds are an input to this batch, not an output** — odds-api.io returns no
retrospective price, so there was nothing to probe and nothing to spend, and a
winning pick scores `round(odds × 10)`, which makes an invented price an invented
leaderboard position. **Nothing invents an outcome either:** the 26 picks were
written `pending` with no points and settled by the same `settle_gameweek` the
evening sweep calls, against the scorelines already ingested from FotMob — so the
coupons say what was picked, FotMob says what happened, and the points are
computed rather than transcribed. A rehearsal against production before anything
was written resolved 25 of the 26 through the real matcher and found **every
FotMob scoreline agreeing with the settled slip's own tick and cross marks**. The
twenty-sixth is Aberdeen v Dundee, which is Scotland League Cup Group C — a
competition no source carries, alongside NI Championship 1 and the English
non-league tiers — and its 3–0 came from the slip and the owner independently,
through a fallback that may only fill a hole and never override stored data.
**Applied to production on 2026-08-24**: three rounds settled, 36 settled picks,
zero points mismatches against `round(odds × 10)`, and a 24-leg hand tally
agreeing on every line. All twelve members now show three rounds played.

Batch 61 raised the framework, and found a guard that had been walking nothing.
`fastapi 0.141.1 / starlette 1.6.0 / pydantic 2.13.4` clears the last of Batch 59's
advisories — all of them `starlette 0.37.2` pinned by `fastapi==0.111.0`, and all
unreachable here, so this was hygiene rather than an emergency. The three move as a
set because FastAPI 0.141 requires pydantic ≥ 2.9, and 19 transitives that 0.111
bundled disappear with them; none was used, and `routers/auth.py` already recorded
that avatar upload reads the raw request body *specifically* so `python-multipart`
never became a dependency. **The serious finding is `test_wire_datetimes.py`.** Batch
43's guard walks the app's own routes so a response model written later is covered
the day it is added — and FastAPI 0.141 stopped copying an included router's routes
onto the parent, so `app.routes` went from 73 `APIRoute`s to **18 routes, none of them
an `APIRoute`**. The guard had not started passing wrongly; it had lost every route in
the application, which is worse, because a guard with no subject looks exactly like a
guard with nothing to report. It now descends by structure rather than by class name,
works on both shapes, and asserts floors as well as named models. It was demonstrated
failing on Batch 43's original bug afterwards. `HTTPBearer` also moved from 403 to 401
for a credential-less caller, which is correct — RFC 7235 reserves 403 for a caller
who *is* authenticated — and the decision was that the web client needs no change:
`lib/api.ts` keys on 401 alone, so the anonymous case moves onto the refresh-then-login
path and improves. Widening it to 403 would sign a member out for reaching an admin
route, and the file now says so. **This is API-side and a `/ship-prod` is owed.**

An unrelated blocker was fixed first, on its own branch (`dfc5291`). The gate was
already red on `main`: `test_round_population.py` asserted on `rounds[0]` and assumed
it was still claimable, but `upcoming_slate_dates` includes today by *date* alone, so
on the league's own weekday after its lock that round is born dead. The test used a
Tuesday window, so it failed on Tuesdays after 18:45 London and passed the other 167
hours of the week.

Batches 73-76 closed the owner's 2026-08-25 list. **Batch 73** stopped a round
claiming to be open while it refused picks: `status` is only the label the hourly jobs
have caught up with, so the badge read Open both before a round's opening instant and
for up to an hour after its deadline. `pickRefusal` in `lib/coupon.ts` is now the
written-down rule, mirroring the API's own. The same defect was on the settings screen
twice over — its round list filtered on `status`, and its copy told admins a change
"never restamps a round that already exists", which Batch 40 wrote correctly and Batch
65 falsified. `PickShapeLine` also lost its longshot split and names its figure
`avg odds selected`. **Batch 74** is a script, not a change: 2-1 Hibs' four rounds
renumbered 1-4 and three members renamed, reversing a decision Batch 68 made
deliberately. It fails closed and is **not yet applied**. **Batch 75** deleted a
nightly `pg_dump` that crossed the internet to write an uncompressed copy of a 12 MB
database into a `/tmp` no volume backed, keeping the same job runnable on demand.
**Batch 76** gave the product the notifications it never had — picks opening, somebody
claiming or moving, and one reminder three hours before the lock instead of one a day —
and closed the gap underneath them: `league_memberships.notification_muted` had existed
since Batch 32 with exactly one query honouring it, so `send_notification` could not
check a mute it was never told about.

Batches 1-72 are closed. The Coupon is a
verified weekly football accumulator PWA whose *leagues* are private — signup
itself is public as of Batch 63 — and it is a **per-league** game: a member may
play in several leagues at once and each owns its rounds, window, markets,
competitions and claim size. Members create their own account with a display
name and PIN, join a league by code or invite link, claim one unique selection
per league per round, score frozen odds after settlement, compare standings,
and view the shared combined coupon. The
single-Saturday, 14:30-lock rule is now the *default* an unconfigured league
plays, not an assumption the schema or the API makes.

Batch 31 closed the multi-league audit's cost half — settlement now reads a
fixture once per run rather than once per league holding it. Batch 32 gave a
member a per-league mute alongside the existing global mute and quiet hours,
so a member in several leagues can turn off one without losing the rest — the
flag lives on `league_memberships`, not a new table, so it dies with the
membership. Batch 34 made the league switcher keep the reader on the surface
they are on: it had pointed every league at its leaderboard, so a member in two
leagues could not change which league's coupon they were reading.

Batch 35 closed the last of the multi-league audit: a one-off round
(`POST /leagues/{slug}/gameweeks`) was the one admin action never checked
against the contract. "This week" is no longer the newest `starts_on` but the
round a league is actually on — among rounds accepting picks now, the one
locking soonest — defined once in `current_round_order` and used by both the
per-league read and the cross-league one, so the Coupon tab and the home card
cannot disagree. The endpoint's `6/hour` limit permitted ~180 provider requests
an hour against a 100/hour allowance and is now `2/hour;3/day`, derived from a
measured budget rather than a modelled one. The ad-hoc fetch asks only for the
competitions the league plays, since nothing shares it. And discovery now walks
the cadence *union* the dates of unlocked rounds, so a one-off is refreshed
rather than frozen at creation.

Batch 36 stopped provider API keys reaching the logs. odds-api.io takes its key
as a query parameter and httpx logs every request URL at INFO, so each odds call
published a live credential into Railway's logs — observed 2026-08-19 in the
running production deployment. Redaction now happens at the JSON renderer, which
covers the message, keyword values, nested structures and any third-party
library in one mechanism, and holds if a quieted logger is re-enabled later;
httpx and httpcore are also quieted to WARNING. **Rotating the exposed key
remains an owner action that this batch does not perform.**

Batch 39 collapsed a league admin's six action buttons into one overflow menu.
Batch 22 had made the row wrap rather than overflow, but six chips folding into
a narrow column beside a `flex-1 min-w-0` title was the same complaint in a new
shape. A member keeps their single `Leave` button in the open, since one button
never overflowed. The Radix dropdown primitive brings focus management,
Escape-to-close and outside-click dismissal, which is the substance of the fix.

Batch 38 made the coupon say *when* a selection was taken, not just who by.
`Pick.created_at` had always been on the row and nothing carried it out. The
field is additive and optional on the client, because Vercel deploys the web app
from `main` while the API waits for `/ship-prod` — a renamed or required field
would break the coupon in that gap.

Batch 42 modelled profile pictures without enabling them, and Batch 44 met the
three conditions it recorded. Uploaded bytes are now **re-encoded** — Pillow
decodes the image and a fresh WebP is written from the pixels, so a payload
riding behind a valid PNG signature does not survive, and a decompression bomb
is refused from its header before a pixel is decoded. The bucket's access rules
are written explicitly (ADR 0006): public-read with an unguessable object key,
because the private-and-signed alternative turns `avatar_url` into a stored path
and every member list into a round trip per picture. Removal already existed on
both sides. **The feature is complete and still switched off**: `AVATAR_STORAGE`
defaults to `none`, so every environment answers 503 exactly as before, and
`GET /api/v1/config` tells the web app to leave the upload card unmounted.
Turning it on is `docs/runbooks/avatar-storage.md` and it is an **owner action** —
it needs the Supabase dashboard and seals a service-role key. This narrows, and
does not overturn, the launch-plan decision to use Supabase as managed
PostgreSQL only: Storage, one bucket, one feature, API-side only.

Batch 43 stamped the UTC offset on every instant the API sends. The columns are
naive UTC and the backend compares naive to naive correctly throughout, but
pydantic rendered that as `2026-08-22T13:30:00` and JavaScript reads an
offset-less date-time as *local* time, so the wall-clock number displayed
equalled the stored UTC number in every zone — a 14:30 London lock shown as
13:30. The countdown ran on the same mis-parsed instant and `locked` derives
from it, so **the pick screen shut an hour before the API stopped taking
picks**. Invisible from late October to late March, and it returns without a
deploy. `UtcDatetime` is applied at the API boundary and a test walks the app's
own routes so a later model cannot miss it. The client parses defensively too,
because Vercel deploys `main` on merge while the API waits for `/ship-prod` —
**until that ship-prod runs, the client half is the only half in production.**
`starts_on` is now rendered as the calendar date it is rather than converted
into a zone, which had announced the round a day early west of UTC. The test
runner's zone is pinned to `America/New_York`: in a UTC process a mis-parsed
instant and a correct one are the same number, which is why 325 green tests
never saw this.

Batch 41 gave the round a name. The coupon showed a date where members expect
"Gameweek N" and no number existed to show; migration 014 adds one and backfills
per league, per season, in `starts_on` order. It is stored rather than derived
because Batch 35 made a one-off round legitimate, and an ordinal recomputed on
read renumbers every round after it the moment one is inserted — a member's
"Gameweek 12" would become a different week. A one-off simply takes the next
number. The number is a display concern only: nothing in locking, settlement or
scoring keys on it, and every read falls back to the date when it is absent.

Batch 37 stopped a lower division resolving to the Premier League. `similarity`
awarded a flat subset bonus whenever one name's tokens sat inside the other's,
so "Southern League, Premier Division South" scored 0.950 against England's top
flight and 0.800 against its real counterpart — the wrong answer above threshold
and the right one below it, confidently and uniquely, so no ambiguity margin
could catch it. The bonus is now withheld on the competition path only (it is
load-bearing for club names), `MATCH_MARGIN` is applied where it never was, and
four divisions the two catalogues do not name alike carry an explicit override
read from both live catalogues. Coverage was never the problem: a probe on
2026-08-19 confirmed the free plan *lists* every British division for season
2026 — what it does not do is serve their standings, which the 2026-08-20 sweep
established the day after. The corrective data cleanup this paragraph used to
say was owed is not: the tables were empty then and are empty now, so there is
nothing mis-ingested to clear. Batch 40 is no longer deferred — it closed on
2026-08-20 by taking the forward-only rule.

Batch 6 completed the product rebrand, removed inherited surfaces, corrected
the frontend auth and invite wiring, and added a deterministic production-
preview browser flow backed by scratch PostgreSQL and `FakeBetfair`.

Batch 7 replaced the Betfair Exchange with `odds-api.io` priced by Bet365,
behind a provider-neutral `OddsProvider` port. This unblocks production: the
Exchange never priced the Scottish lower divisions and refused the production
login from every available region, so no gameweek could exist. Settlement is
now derived from published scores, the schema carries no provider identifiers
(revision `005`), and request-path odds are cached against the provider's rate
limit.

Launch phase L0 records the public repository, fresh project names and
owner accounts, no-cost platform hostname strategy, regions, budget controls,
15-player roster handling, and connector boundaries.

Launch phase L1 hardened the application and deployment path. Launch phase L2
provides fresh, isolated Supabase, Railway, and Vercel staging targets, with
stable web/API origins and a target-specific shipment workflow. Launch phase
L3 verified the full canned-odds staging story, phone push lifecycle,
scheduler, backup/restore, platform logs, and rollback.

Launch phase L4 provisioned and verified the production stack. Production is
deployed, healthy, and serving at
`https://the-coupon-production.vercel.app`, backed by
`https://api-production-109b1.up.railway.app` and a locked-down London Supabase
project holding one bootstrapped administrator.

The odds source works: verified live for Saturday 2026-08-08, `odds-api.io`
carries 30 UK leagues, 131 qualifying 15:00 fixtures, and 280 distinct priced
selections against the 15 a full league needs, with both Scottish lower
divisions fully priced.

**Production runs `1272dde` on both stacks as of 2026-08-21**, at migration
`015` — Railway `854a24ec`, Vercel `dpl_FfGCr4FcbFaGnzaEzN33D6qAHFVE`. That
shipment carried Batches 47 and 48, closing the gap the Batch 48 close-out had
left: the new-league-rounds fix and the odds-provider-degradation fix are both
now live, and `main` and the API agree again. `/api/v1/health` reports that
commit and the migration head bundled in the image, so
`scripts/check-deploy-drift.sh` answers exactly (`in sync`) rather than falling
back to probing. `ODDS_API_KEY` is sealed and rotated, `ODDS_PROVIDER=oddsapi`,
and `SCHEDULER_ENABLED=true`; the paragraph above about a Betfair build and an
unsealed key described the state before the 2026-08-04 and 2026-08-06
shipments.

That shipment took 91 minutes for reasons that were **not** the build: Railway
paused deploys platform-wide while the container was already running, so the
`HEALTHCHECK` deployment event hung for 83 minutes past its own 300-second
timeout before completing on its own. `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md`
records how to recognise it — a stalled step with a healthy container is a
platform problem, and `railway up` refuses outright with
`Deploys have been paused due to an upstream issue`. Production served the
previous deployment throughout. Note that a stall of that kind leaves **two
schedulers running**; nothing double-fired here, but it would have reached the
11:00 pick reminders had it lasted the night.

The football-data provider is **switched off in production**
(`FOOTBALL_DATA_PROVIDER=none`, owner decision 2026-08-20), and the Football tab
is empty because there is nothing to show it. That closes a question this file
carried for weeks. Batch 16 built the feature, Batch 28 found the undocumented
10/minute ceiling, and Batch 33 found what that was hiding in the catalogue —
but the 2026-08-20 sweep, the first to get past all three, answered the real one:
**api-football's Free plan carries no season after 2024.** Not the lower
British divisions — *nothing*, the Premier League included. All 18 competitions
that resolved a league id were rejected at `/standings` with *"Free plans do not
have access to this season, try from 2022 to 2024"*; the remaining 3 are cups
that resolve no id and have no table anyway.

A follow-up probe the same day, run with the sealed key via `railway run`, showed
that the sweep had understated it twice. The refusal is **plan-wide, not a
`/standings` problem**: `/fixtures` and `/teams` refuse season 2026 with the
identical error, and `/fixtures` with a date window and no season is rejected
outright (*"The Season field is required"*), so there is no way round the gate.
And **season 2025 is refused too** — the most recent data the plan can reach is
2024/25, which ended 2025-05-25, two seasons back. The key is valid, the plan is
active to 2027-07-24, and season 2024 returns a complete table. This is an
entitlement wall, not a defect, and no amount of code fixes it.

`teams`, `team_aliases`, `matches` and `standings` are empty and have never held
a row, in any environment. The team-matching defect this was read as does not
exist: `/standings` fails before a single team is stored, so the candidate list
is empty and `candidates=0` follows from that, not from a name that failed to
match. Anyone reopening this should start at the plan, not the matcher.

That question now has an answer: **FotMob replaces api-football as the
football-data provider** (ADR 0007, owner decision 2026-08-20), scoped as Batch
46. It was the only free source found that carries the English step 6-7
divisions — National League North and South, Southern Premier Central and South,
Northern Premier, Isthmian Premier — which are 203 fixtures, **49% of the card**.
FotMob carries 17 of the 18 leagues and 368 of the 389 league fixtures, missing
only `northern-ireland-championship-1`. The alternatives were measured, not
assumed: football-data.org's free tier is 12 competitions (British ones the
Premier League and Championship only), TheSportsDB truncates every table to five
rows, and football-data.co.uk publishes no tables at all.

The trade is recorded rather than glossed. FotMob's terms prohibit automated
access, and its interface is undocumented and moves — `/api/leagues?id=47`
already 404s, and the working path is `/api/data/allLeagues`. ADR 0007 holds both,
and TheSportsDB at roughly $9/month is the measured fallback.

Turning it back on stays one variable (`FOOTBALL_DATA_PROVIDER=fotmob`) but now
waits on Batch 46's adapter. Pinning `FOOTBALL_SEASON` to 2024 was never the
workaround it looked like — it would render tables and form from **two** seasons
back against 2026/27 fixtures.

Batch 45 fixed the reason this took so long to see. The sweep failed all 21
competitions, logged `football data synced`, and exited `0`, because
`run_sync_football_data` returned `True` on any run that reached the provider —
so the 06:30 cron reported a healthy run every morning while ingesting nothing.
A list of reports could never answer the question: a competition that *raised*
leaves no report, so an empty list meant both "the card was empty" and "every
competition failed". The sweep now carries how much of the card it attempted,
and a run that attempted a non-empty card and carried none of it is a failure —
which `run_scheduled` already turns into a non-zero exit. The per-competition
tolerance is untouched: one division the provider dropped still must not cost
the other twenty-nine their tables.

Note that the two stacks ship differently: **Vercel auto-deploys `main` on every
push; Railway moves only when `/ship-prod` runs.** Between 2026-08-04 and
2026-08-06 that let the API fall thirteen batches behind the web app and broke
the Coupon tab in production. `scripts/check-deploy-drift.sh` reports the gap
and `/phase-closeout` now runs it.

Launch also ships with **no database backup**, by owner decision recorded in
`docs/launch/L0_PROJECT_IDENTITY.md`.

Batches 8 onward come from the owner's 2026-08-05 feedback pass and proceed
alongside launch. Batch 8 bound the coupon, combined-acca, and home pages to
`LeagueContext`'s new `activeSlug` (last-viewed league, falling back to the
member's first league) instead of the hardcoded `DEFAULT_LEAGUE_SLUG`.

Batch 9 reshaped the pick screen: the slate groups by competition behind
collapsible headers, a member roster shows every member's pick and who is still
to pick, each fixture carries an "already picked" marker beside the existing
per-selection one, and `profiles.odds_format` (migration `007`) lets a member
read prices as decimal or traditional UK fractional. The format is display only
— prices stay `Numeric(6, 2)` and a winner still scores `round(odds × 10)`.

Batch 10 added `leagues.pick_scope` (migration `008`): a league may make one
claim take the whole game rather than a single selection, enforced by a partial
unique index on a scope denormalised onto each pick. The default is unchanged
behaviour, so opting in is deliberate — it shrinks the pick pool roughly
fivefold, which a 15-member roster feels.

Batch 11 split fixture discovery from pricing. A daily 06:00 job walks the next
two Saturdays into `fixtures` at a fixed cost; odds stay on demand behind a cache
whose freshness ceiling tightens as lock approaches, with the price frozen onto a
pick refreshed separately for that one fixture. `tests/test_request_budget.py`
asserts the whole arrangement against the provider's 100/hour and 500/day — the
daily cap is the binding one.

Batch 12 made the season browsable. A gameweek list endpoint plus a `gameweek_id`
parameter on the slate and coupon reads replaced the hardcoded `latest_gameweek`,
and the client keeps the selection in the URL so a past week is linkable. Every
gameweek ever synced is retained, so the history needed no backfill.

Batch 13 added a per-league member profile at `/leagues/:slug/players/:playerId`:
season figures taken from `standings()` so the two cannot disagree, a win rate,
and every settled pick behind them. Per-league rather than career-wide, because
picks are league-scoped and the claim rule is too.

Batch 14 split the schema so leagues can play different football. `gameweeks` is
per-league (migration `009`, `saturday_date` renamed `starts_on`), fixtures are a
shared pool joined through `gameweek_fixtures`, and the weekly window — which days,
which kick-off times, how long before lock — is per-league configuration stored as
a range. Defaults reproduce the Saturday 15:00 slate exactly. Discovery groups
leagues by window so a second league on the default costs no extra provider
requests.

Batch 15 put those settings under admin control and added two more. The fixture
window is now editable (Batch 14 only stored it); a league also chooses its
competitions — `leagues.competitions` (migration `010`), `NULL` for the "all UK
leagues" group or an explicit list applied as a link-time filter in `sync_slate`, so
narrowing costs no extra provider requests — and its offered markets, a subset of the
`pick_market` enum stored as an array. Admins can add a one-off round for a date off
the usual cadence, such as Boxing Day. All of it is gated by `LeagueAdminDep`.

Batch 16 added real football. Tables, previous results, and form come from a
second, independent provider (API-Football, ADR 0003) because `odds-api.io`
publishes no standings, and our own fixtures could not supply a table — the slate
has only ever stored Saturday 15:00 kick-offs, and scores were never persisted.
Migration `011` adds `teams`, `team_aliases`, `matches`, and `standings`; a match
is a separate record from a fixture, since most matches are neither pickable nor
picked. The free plan allows **100 requests a day**, so no screen ever reaches a
provider: a capped, rotating 06:30 job writes the tables and every read serves
them. Team names are reconciled between the two providers' spellings by an alias
layer that refuses to guess. Two surfaces — a Football section at
`/predictions/football`, and each club's position and form inline on the pick card,
which degrades to the pre-batch card when a club does not resolve.
`FOOTBALL_DATA_PROVIDER` defaults to `none`, so production is unchanged until the
owner runs a live probe and seals a key.

Batch 17 was a timeboxed spike and ships no code — its output is ADR 0004, which
decides **not** to build betslip export. Bet365 publishes no betslip API; Bet Share
carries a full accumulator but only a logged-in Bet365 customer can mint one; the
affiliate add-to-betslip link is one we could create and carries a single
selection. Two walls settle it either way: nothing we can generate composes an
accumulator, and `odds_at_pick` is frozen, so an exported acca prices live at the
book and disagrees with the coupon's headline number. An outbound bet link would
also make this gambling advertising, and there is no age gate anywhere in the
application. The combined coupon stays a scoreboard.

Batches 18 onward come from the owner's 2026-08-06 feedback pass, reconciled
against the code before being written up. Batch 18 was a live production defect
found while reconciling it, not one of the five reported points: `vercel.json`'s
SPA rewrite sent every self-hosted font and PWA icon to `index.html` because its
negative lookahead excluded a directory (`icons/`) that never existed rather
than the actual root-level paths, and the service worker precached the HTML
substitutes into the installed app. Fixed by correcting the lookahead to match
`fonts/`, `icon-`, `apple-touch-icon.png`, and `coupon-icon.svg`.

Batch 19 diagnosed and fixed the owner's coupon-page crash report: not coupon
code, but a stale route chunk. Every route is `lazy()`, a deploy drops the
previous build's chunk hashes, and `sw.ts`'s `skipWaiting()`/`clientsClaim()`
hands an open tab to the new worker while it still runs old JS, so the first
route change after a deploy 404s. `lib/lazyRoute.ts` (ADR 0005) wraps
`React.lazy` for all eighteen routes and `Layout`, reloading once on a
recognized chunk-load failure and otherwise letting `ErrorBoundary` explain.

Batch 20 fixed three reported wayfinding gaps, all frontend-only with no API
change: the home page now names the active league in its `PageHeader` eyebrow
(covering all three home cards); a self-profile route now exists, reachable
from both `TopBar`'s avatar menu and `TabBar`'s mobile More sheet as "My
profile"; and the already-built `LeagueJoinRequestsPage` and
`LeagueAdminInvitesPage` gained admin-only buttons in `LeagueActionsMenu`.
Also fixed in passing: `SettingsPage`'s dangling `/about` link, which had no
route and silently bounced through the catch-all to home, now resolves to a
new `AboutPage` reusing the existing scoring-rules copy.

Batch 21 fixed the competition picker Batch 15 shipped, which was empty for
most leagues so "all UK leagues" was the only usable choice. The cause was the
catalogue, not the UI: `GET /{slug}/competitions` built its list from
`SELECT DISTINCT … FROM fixtures`, which is only what discovery had already
pooled, so a league whose slate had never run had nothing to tick. The odds
port gained `fetch_competitions()` as an `@abstractmethod` — a default
returning `[]` would have left `FakeBetfair`, which backs staging and the
browser flow, showing that same emptiness. It costs no upstream request on the
common path: the catalogue is one `/leagues` call memoised on the shared
client, not the per-competition `/events` fan-out the slate pays for. The
pooled-fixtures query survives as the fallback when the provider is
unreachable, because the picker is also how an admin *un*-narrows a league.

Batch 22 fixed the 2026-08-15 wayfinding and layout feedback without changing
the API contract. Football is now in primary navigation on both desktop and
mobile, with active state kept distinct from Coupon. `PageHeader` lets its
action slot shrink so `LeagueActionsMenu` can wrap on phones; Members is
admin-only; and both combined-coupon legs and player history rows render the
competition already present on `CouponLeg` and `SettledPick`. The close-out gate
also found and fixed a backend config trap: `apps/api/alembic.ini` had a
non-ASCII comment that made Alembic config parsing fail under an ASCII locale,
so `/health` could report `migration: unknown` even though revision `011` was
bundled.

Batch 23 made the large-slate picker scan by competition first. The gameweek
API now includes `fixtures.competition_id` in each `FixtureSlate`, and the web
groups on that stable provider slug rather than display names that may carry
sponsor text. Groups start collapsed and sort by the UK league pyramid —
England's top four tiers, Scotland's top four, then each nation's remaining
tiers, then everything else by fixture count. The member roster also carries
and renders the picked fixture's competition.

Batch 28 fixed API-Football ingestion rate limiting, deliberately ahead of
Batch 22. API-Football's free plan is not just 100/day; it is also 10/minute,
and the minute limit arrives as HTTP 200 with `errors.rateLimit`, so the old
429/5xx retry path never ran and the two-requests-per-competition sweep burned
through the minute allowance in seconds. The adapter now treats `rateLimit` as a
transient body error, and the scheduled sync spaces competition attempts by a
configurable 12 seconds so a 30-competition sweep takes about six minutes.
ADR 0003 now records both limits.

Batch 24 added a "Copy text" button to the combined coupon rendering every leg,
selection, price and the combined odds as plain text a member can paste into a
group chat, with a note that prices were frozen at pick time. No bookmaker
link and no new API surface — `buildCouponShareText()` is a pure function over
the fields `GET /leagues/{slug}/coupon` already returns, satisfying the second
wall ADR 0004 left standing.

Batch 25 added a gameweek results view. `GET /leagues/{slug}/results` returns
every settled round, newest first, with its winner (or tied winners), their
points, and the combined-coupon outcome — one query over `picks`, no new
table. The coupon tab gained a Results list alongside Your pick, Combined
coupon and Football, each row opening that week's coupon; the player profile
now links to it too, since it previously listed a member's settled picks
without ever saying how the week went around them.

Batch 26 made home and the profile answer for every league a member plays
rather than for whichever one was bound. `GET /api/v1/me/cross-league-summary`
returns the season across all of them in five fixed queries, carrying a
per-league breakdown plus that league's current round; `scoring.standings()` is
now a one-league wrapper over a new `standings_by_league()`. Points and win rate
aggregate (one `round(odds × 10)` scale); rank does not, so the average skips
leagues with fewer than three members and says how many it covered. Home is a
card per league — its pick, its standing, one tap to that week's coupon — and My
profile moved to a career-scoped `/profile`, in the tab bar and the avatar menu
alike. The per-league record at `/leagues/:slug/players/:playerId` is unchanged.

Batch 29 fixed the same gap on the coupon surfaces that Batch 20 fixed for
home: `CouponPickPage`, `CouponCombinedPage`, `ResultsPage` and `FootballPage`
now name the bound league in their header and render `LeagueSwitchStrip`
above `CouponSubNav`, so a member in several leagues can tell whose slate they
are picking from and switch without leaving the tab. `LeagueSwitchStrip` now
binds through `selectLeague` rather than writing the recency store alone,
closing a drift where browsing `LeaderboardPage` (URL-driven slug) updated
the store but not `activeSlug`, so a later tap on Coupon could reopen the
wrong league. All four surfaces' queries now gate on a resolved membership
(`LeagueContext`'s new `hasLeagues`) instead of firing at the
`DEFAULT_LEAGUE_SLUG` fallback, and a member of no league gets its own empty
state instead of a 404 read as "no coupon yet". Frontend-only, no API or
route change — slug-addressed routes are Batch 30.

Batch 30 gave each league's coupon an address. The four surfaces moved to
`/leagues/:slug/predictions[/coupon|/results|/football]`, so a week can be
linked, shared, bookmarked and reopened at the league it came from, and two
tabs can hold two leagues at once. The slug-less paths still land: they wait
for the member's leagues and redirect through the bound one, carrying the query
string so an old `?gw=` link survives — which also makes `useGameweekHistory`'s
promise true, since a gameweek id is league-scoped and the URL holding it was
not. The URL is now the source of truth: `useRouteLeague` binds the context on
arrival, so `activeSlug` is the default for an address naming no league rather
than the thing addresses derive from, and the binding left `LeagueSwitchStrip`
and home's select-then-navigate pair. The nav bars aim at the bound league but
highlight for any league's coupon. The pick reminder — the reason the addresses
were missing — now carries `url` to that league's pick screen instead of
letting `sw.ts` fall back to `/`, and reads the round's own `locks_at_utc` on
the member's clock rather than hardcoding "picks lock 14:30", which has been
wrong for any league not locking Saturday since Batch 14.

Batch 31 closed the last path whose provider bill multiplied by league count.
Settlement de-duplicated fixtures *within* a league and never *across* them, so
two leagues playing the same Saturday paid separately for every match they both
held — against a plan allowing 100 requests/hour, which roughly seven leagues on
one window would exhaust outright. `settle_gameweeks_via_provider` now gathers
every settleable round's outstanding fixtures, de-duplicates them across the
whole run, reads the provider once, and fans the settlements back out per round;
the cost is the number of *distinct* fixtures outstanding, not the number of
leagues holding them, which is the rule `discover_fixtures` already applied to
slate windows. It works because a fixture is one pooled row since Batch 14. The
row's second, more ambitious step — replacing the per-fixture `/events/{id}` walk
with a windowed read of the `/events` list — was **not** taken: whether that list
carries `scores` for finished fixtures is unverified, confirming it needs a live
odds-api call, and there is no key in the working tree. The open question is
recorded on `OddsApiProvider._event_by_id`. This was latent rather than broken —
running out of quota raises no error, it just leaves picks `pending` and the week
unfinished — so it had to land before the roster of leagues grows, not after.

Batch 47 gave a new league its rounds at creation. Discovery runs once a day at
06:00, so a league created at any other hour had no round, no card and no coupon
until the next morning, and the only remedy was `discover-fixtures` inside the
production container — an owner action for a problem every admin hits. It is
nearly free, because `discover_fixtures` already fetches each `(window, date)`
once and shares it: `pooled_slate` reads a window's card back out of the shared
`fixtures` pool, so a league on the default Saturday everyone else plays is
`sync_slate` against rows that exist and costs **zero** provider requests.
`populate_cadence_rounds` walks the cadence and nothing else — an off-cadence
date belongs to the league that asked for it — and falls back to a real fetch
only where the pool is empty. That fallback is charged one unit per sweep to
`PROVIDER_SLATE_FETCH_LIMIT`, the ad-hoc round endpoint's `2/hour;3/day` renamed
now that three routes share it, through `limiter.shared_limit` on the route and
`consume_shared_limit` in the populate path, so the two cannot be combined to
exceed the budget and a pooled populate charges nothing. The same path is an
admin action — `POST /leagues/{slug}/gameweeks/refresh` and a Rounds card on
league settings — because an admin who moves the fixture window has rounds built
against the old one. Creation resolves the provider through a new
`OptionalOddsProviderDep`, so a provider outage leaves a league with no rounds
*yet* rather than failing the creation. Both ends of a round's claim period stay
stamped as created, and a locked or settled round is skipped rather than rebuilt.
No migration, and `discover_fixtures` keeps its cadence-union-off-cadence
behaviour exactly as Batch 35 left it.

Batch 48 stopped the pick screen dying with the odds provider. `_live_odds` called
`fetch_odds` with no fallback, so any provider failure propagated and
`GET /leagues/{slug}/gameweek/current` returned 500 — the screen every member opens to
make their pick had its availability wired to a third party's rate limit. Observed in
production on 2026-08-21, the day before launch, when `/odds/multi` answered `429` and
the Football tab beside it kept working because it reads only the database. The cache
already held the remedy: when an upstream call raises, its entries are still there,
merely past their TTL. `fetch_odds_best_effort` catches the failure and falls through to
them, returning an `OddsSnapshot(odds, degraded)` — last known prices, or a card with no
prices at all, which still shows the fixtures. **The pick path is untouched and still
raises**, because a winner scores `round(odds x 10)` from the price frozen at that
instant, so a stale one is not a degraded pick but a wrong score; an unreachable provider
now refuses the submission with `503 ODDS_UNAVAILABLE` rather than crashing. `_get` no
longer retries a `429`: retrying "you are over budget" is the one response guaranteed to
keep you over it, and the three retries with doubling backoff turned a single rate-limited
slate load into four upstream calls, which is how that afternoon's breach sustained
itself. 5xx and network errors retry as before. The slate carries `odds_degraded` and the
pick screen says "prices may be out of date" — additive and optional, because Vercel
deploys `main` on merge while the API waits for `/ship-prod`. No schema change, and the
TTL tiers are untouched.

Batch 49 stopped a called-off fixture staying pickable. `sync_slate` said it
outright — "Links are added, never removed" — so a fixture postponed after
discovery stayed on every round that had linked it and stayed claimable right
through the deadline, because nothing between discovery and the evening settle
sweep read the provider's status: `fetch_slate` built each `SlateFixture` from
the teams and the kick-off and dropped the rest, while `_VOID_STATUSES` was
consulted only by `_settlement_for`, hours after the round had been played.
`SlateFixture` now carries the provider's own word verbatim, the void vocabulary
moved to `odds_provider` so discovery and settlement cannot disagree about what a
postponement is, and `_drop_voided_fixtures` takes the link *and* the pick off an
open round — two deletes, because `gameweek_fixtures` is a composite-key join
with no cascade to `picks`, so unlinking alone leaves a pick off the screen and
still visible to settlement. It stops at the lock, gated on `locks_at_utc` rather
than the status label: a member who picked before the deadline cannot respond
after it, and settlement already writes `void` for exactly this status. Absence
never removes anything — a partial or failed fetch is indistinguishable from a
quiet one — so only an explicit status acts, and the empty default means a
Betfair catalogue and a pooled rebuild cannot unlink at all. The member is told
via a free-form `fixture_postponed` push and left with *no pick*, the one state
the game already understands. **Live probing found a third answer the plan had
not anticipated:** odds-api.io does emit void words (2 of 1,599 fixtures for
2026-08-22 came back `cancelled`) but was still returning the Hibernian v
Kilmarnock fixture as `pending` after it had been called off — so this closes the
general case, not the observed one, and settlement remains the backstop. No
migration: the status rides the DTO, because the pooled row stays for the leagues
still linking it.

Batch 50 fixed three omissions on the pick card, frontend-only. The context
strip and the team names now share one `grid-cols-2` container instead of an
inline sentence sitting over a separate grid, so a club's form aligns under
its name by construction rather than by text-length coincidence. The "Your
pick" summary on `CouponPickPage` now names the competition, matching
`CombinedAccaView`'s per-leg format. And `potentialPoints()` — a pure
`round(odds × 10)` of the displayed price — now stays visible alongside
"taken by X" and "your pick", not just on an unclaimed selection.

Batch 51 untied Football Stats from a league. The tables and results screen read
`/leagues/{slug}/football/…` and narrowed to the competitions that league plays,
which was never what it is for: a member opens it to look at football, not at the
subset of football their own coupon covers. **The data was never league-scoped —
only the read was.** `pooled_competitions` already walked the whole shared fixture
pool and `teams` / `matches` / `standings` carry no league column, so untying it
cost nothing upstream: no ingestion change, no migration, and the 100-a-day
API-Football budget is untouched. `/api/v1/football/tables` and `/results` now
take no slug and are gated on an authenticated player rather than
`LeagueMemberDep` — the router's own docstring had already conceded that gate was
consistency rather than privacy. The old routes and `league_competitions()` are
deleted rather than left dead. Because `CouponSubNav` is explicitly league-bound,
the tab left it for a top-level `/football`, and `LeagueSwitchStrip` came off the
page, where it would have been a control that changed nothing; the two old
addresses redirect. Renamed **Football Stats** while the nav was being edited —
57.7px in a 75px tab at 375px and a 64px tab at 320px, so it stays on one line on
the narrowest phone. One limit is recorded in the empty states: the pool holds
only competitions some league's card has drawn from, so "untied" means every
competition we have ever ingested, not every competition in Britain.

Batch 52 fixed two omissions the football screen's own docstrings named, frontend-only.
`LeagueTableCard` hid Form below `sm` to keep played/won/drawn/lost on screen without
sideways scrolling — the right call for those four counts, wrong for form, which is a
glanceable five-glyph run and one of the two things a member opens the screen to read.
Goal Difference now carries the `narrowHidden` flag instead; Form does not. Results were
grouped by day alone, so a Saturday read as one undifferentiated column across every
competition a member's coupon draws from; `groupByDay` now nests by `competition_id`
within each day, with a competition heading only when a day actually holds more than one.
Both fields — `form` and `competition`/`competition_id` — were already served, so no API
change and no migration.

Batch 53 stopped the form pips discarding what they are made of. `TeamContext.recent`
had carried every match behind a fixture's form line since Batch 16 — opponent, home or
away, goals both ways, result, kick-off — and `FormLine` took `form: string` and threw
the rest away on render. A run now opens onto its results on both surfaces. On the pick
screen that needed no API change; in the league table it did, so `TableEntry` gains an
optional `recent`, loaded through the same one-statement `team_form()` call
`fixture_context` already makes rather than a query per club. `league_tables()` now
derives the form *string* from those matches instead of trusting `standings.form`, which
the provider writes from a different upstream call and which can disagree with what is
stored in `matches`; the stored string survives only as the fallback for a club with a
table line and no matches, whose pips the client leaves inert rather than opening onto an
empty panel. Becoming a disclosure also moved the run off `role="img"` — that role
swallows its subtree and leaves `aria-expanded` nothing to describe — onto a real button
carrying the same accessible name. The panel is placed by the caller, never in the Form
cell, which at phone width would have forced the sideways scrolling Batch 52's hidden
columns exist to prevent.

## Verified

- Backend: 660 pytest with a database, Ruff check/format, and
  strict mypy; Batch 53 close-out passed `scripts/ci-local.sh` end-to-end
  (11 checks), as every close-out since Batch 26 has. That script's pinned venv **is**
  the gate: app-starter's venv can no longer even collect the suite (no Pillow, so
  `avatar_storage.py` takes ten test files down with it) and `AGENTS.md` plus
  `docs/agent-commands/batch-verify.md` still document that stale path
- Database: clean `pgserver` migration through revision `013`, including a pre-009 backfill, a 009 downgrade round-trip, and a 010 up/down round-trip, with forced RLS
  on all 18 public tables under a Supabase-like role setup. The count was 13 at
  revision `004`; `009`-`013` added the rest, and every one of the 18 was
  confirmed RLS-enabled *and* forced against production on 2026-08-19, with
  `anon`, `authenticated` and `PUBLIC` holding no table privileges and no schema
  `USAGE`
- Frontend: Node 20 production build, TypeScript, ESLint, and 387 Vitest, the
  suite now pinned to a non-UTC zone (`America/New_York`) so an instant parsed
  as local time cannot pass unnoticed
- Browser: production-bundle smoke plus the full live staging story, including
  deep links, auth, administration, picks, settlement, standings, combined
  coupon, phone push, and PWA update behavior
- Repository: inherited-name and stale-file audit clean
- Launch L0: owner-approved public GitHub origin, explicit fresh platform
  targets, scoped Supabase connector boundary, and recorded owner decisions
- Launch L1: durable PIN lockout, inactive-login rejection, removed avatar
  upload/passwordless activation/public reset/Sentry surfaces, staging-only
  `FakeBetfair`, Betfair certificate-login support, scheduler retries,
  migration-level Supabase Data API lockdown, deployment runbooks, CI coverage,
  and clean PostgreSQL-backed tests
- Launch L2: fresh London Supabase staging at migration `004`, one always-on
  resource-capped Amsterdam Railway replica, Vercel `apps/web` staging, stable
  origins, synthetic-only seed data, sealed staging configuration, and
  verified Data API denial
- Launch L3: CI and the complete synthetic staging story, exactly-one
  scheduler exercises, phone push subscribe/send/unsubscribe, clean platform
  logs, a disposable logical restore, recorded evidence, and tested rollback
  with the reviewed forward deployments restored

- Launch L4: London Supabase production at migration `004` with forced RLS,
  denied Data API and clean advisors; sealed Railway and Vercel production
  configuration; healthy first deployments with confirmed alias, TLS, CORS and
  SPA deep links; an idempotent administrator bootstrap with verified counts
  and end-to-end login; and clean production logs. Three Betfair defects found
  by live probing were fixed: certlogin field names, sponsored English
  competition names, and a division allow-list that starved the slate.

Batch 27 made the pick-open time a league setting. A round previously became
claimable at whatever moment `run_refresh_slate` happened to write it, which was
neither announced nor the same each week. `leagues.pick_open_offset_minutes`
(nullable) sits beside `lock_offset_minutes` and is measured back from the same
anchor, so a bigger number is earlier and the two must satisfy
`pick_open >= lock`. `gameweeks.picks_open_at_utc` is the derived instant, frozen
at discovery and never re-derived, so editing the setting cannot move a deadline
members were already told. `GameweekStatus` gained `scheduled` for a round that
exists but has not opened, and `pick_refusal` is now the single gate, answering
`PICKS_NOT_OPEN` as well as `PICKS_LOCKED`. Time decides both ends and `status`
is only the label the hourly open/lock jobs keep up with. `NULL` preserves the
old behaviour exactly, so migration 012 needs no backfill and no existing league
changes. The offset stays off `SlateWindow` on purpose — `discover_fixtures`
groups by window, so putting it there would multiply the provider bill.

## Next

`docs/BUILD_PLAN.md` carries **one unchecked batch**: **Batch 77**, written on 2026-08-26
after the defect it describes was hit in production. 61 and 73-76 all closed on
2026-08-25/26 and are shipped.
`docs/LAUNCH_PLAN.md` has a single open phase, **L5 — Launch and first-Saturday
watch**, with L0-L4 ticked since 2026-08-04.

**Batch 74 was applied and the API shipped, both on 2026-08-26**, so the two items
previously owed here are done: production serves `a7573e32`, `/api/v1/health` and
`/health/ready` agree at migration `016`, and `check-deploy-drift.sh` reports **in sync**.
2-1 Hibs' rounds read Gameweek 1-4 and the three renamed members carry their new names.

What is outstanding now:

**Craig Robinson, Marc Birch and Lewis Steele have not been told their sign-in names
changed.** Nobody was signed out — the JWT subject is the player id — so this surfaces
only at the next session expiry or PIN reset, which means the failure arrives days later
looking unrelated. `Craig`, `Birch` and `Lewis` are also now registrable by anyone, since
a rename releases a name outright where a deletion would have kept it reserved.

**Batch 77 is open**, written after 2-1 Hibs hit it live: the owner set
`pick_open_offset_minutes` to 720 on 2026-08-26, `rederive_claim_periods` stamped the
opening onto Gameweek 4 correctly, and left it labelled `open`. Picks were refused
correctly throughout and the badge read correctly — but `open_due_gameweeks` selects
`scheduled` rounds only, so it could never have fired Batch 76's picks-open notification
for that round. **Gameweek 4 was corrected by hand**; the batch is so it stops recurring.

**Production still has no managed backup and no PITR** (the owner's 2026-07-30 deferral).
Batch 75 removed a nightly dump that `/tmp` destroyed on every redeploy, which changes
nothing about recoverability but stops the logs claiming a backup happened. This remains
the largest standing risk and it needs an owner decision before it needs any code.

**What actually spent the Supabase egress quota is still unknown.** Supabase meters per
*organisation*, so the consumer may not be this project at all.

Batch 53 closed the last of them: a form line now opens onto the matches it is made
of, on the pick card and in the league table. **It is API-side as well as web, and
the two halves separate on merge** — Vercel takes the client immediately while the
deployed API still serves `TableEntry` without `recent`. That field is optional for
exactly this window, so the table degrades rather than breaks: its pips simply will
not open until a `/ship-prod` runs. The pick screen's half needed no API change and
works on merge. **A `/ship-prod` is owed.**

Batch 52 closed the one before that, frontend-only with no API change: the Form
column no longer hides on a phone — Goal Difference drops instead — and results
within a day now group by competition rather than reading as one undifferentiated
column.

Batch 51 closed the one before those: Football Stats no longer narrows to the
competitions the reader's own league plays, and no longer lives under a slug.
**It is API-side as well as web, and the two halves separate on merge** — Vercel
takes the new top-level `/football` screen immediately, while the deployed API
still serves only `/leagues/{slug}/football/…`, which the untied page does not
call. Until a `/ship-prod` runs, the tab reaches production and its two requests
404. This is the sharper form of the usual gap: the batches before it left
production merely *stale*, this one leaves a screen broken until the API ships.

Batch 50 closed the one before that: the pick card's misaligned form strip,
unnamed competition and vanishing points, all frontend-only with no API change.

Batch 49 closed the one before it: a fixture the provider reports called off now comes
off an open round with the pick on it, before the deadline rather than at the
evening settle sweep. **It is API-side and has not shipped** — Vercel deploys
`main` on merge while the API waits for `/ship-prod`, so production keeps carrying
a postponed fixture on the card until one runs. Batch 48 closed the one before it:
the pick screen no longer dies with the odds provider — a failed refresh is
served from the cache's own entries with an `odds_degraded` flag instead of a
500, the pick path still refuses rather than freezing a price it could not
confirm, and a `429` is no longer retried into four. Batch 47 closed the one
before that: a league created at any hour but 06:00 now gets its cadence rounds
immediately, from the shared fixture pool and usually for no provider requests at
all, with the same path exposed as a "refresh rounds" admin action. **Those two
shipped to production on 2026-08-21** (`1272dde`, Railway `854a24ec`, Vercel
`dpl_FfGCr4FcbFaGnzaEzN33D6qAHFVE`); the gap where the API lagged the web half
was closed then and has reopened with Batch 49.

Batch 46 added FotMob as a
third implementation of the football port (ADR 0007) — the first source that
carries the current season, and the only free one reaching the six English step
6-7 divisions that are 49% of the card. It **ships dark**:
`FOOTBALL_DATA_PROVIDER` still defaults to `none`, and turning it on is one
variable plus a staging sweep. The shape that made it interesting is that one
FotMob league id serves up to four of our competitions, the table splits by
group but the match list does not, and the split is recovered by team id rather
than by name. Batch 40 closed the one before it
by taking the **forward-only** rule rather than building an admin restamp: a
2026-08-20 production read showed a single affected round holding zero picks, so
the problem was transitional, not ongoing. What shipped is visibility — the
league settings page now lists the rounds an opening time can still apply to and
says what each will actually do, including the case that reads as "my setting was
ignored", which is a round carrying `picks_open_at_utc = NULL` and therefore no
opening gate at all. The odds-api.io key exposed in the logs
before Batch 36 was rotated by the owner on 2026-08-20. Batch 37's production
data cleanup is no longer owed: `teams`, `team_aliases`, `matches` and
`standings` were confirmed empty in every environment on 2026-08-20 and have
never held a row, so there are no mis-ingested rows to clear.

Launch L5 — launch and first-Saturday watch — is the remaining launch work.
Batch 7 shipped the odds source. Every closed batch through **48** is in
production: the 2026-08-21 shipment of `1272dde` carried Batches 47–48, after
`16a64eff` carried Batch 46 and `33191ba2` carried Batches 43–45. **Batches 49
and 51 are merged and not shipped** — both are API-side, and Vercel takes `main`
on merge while the API waits for `/ship-prod`. Batch 51 is the sharper case: its
web half reaches production immediately and calls `/api/v1/football/tables`,
which the deployed image does not serve, so Football Stats 404s until the API
ships. `scripts/check-deploy-drift.sh` reports the gap. What remains:

- ~~seal `ODDS_API_KEY` into production and confirm `ODDS_PROVIDER=oddsapi`~~ — done;
- ~~ship staging and then production~~ — production is at `33191ba2` / migration `015`;
- ~~migrate staging from the deprecated `BF_FAKE_MODE` to `ODDS_PROVIDER=fake`~~ —
  done 2026-08-20: staging is `ODDS_PROVIDER=fake` and carries no `BF_*` at all;
- ~~re-run `.launch-private/weekend-fixtures.py` against the launch Saturday~~ —
  done 2026-08-20 for **Saturday 2026-08-22**: 134 qualifying 15:00 fixtures, 112
  of them priced, **474 distinct priced selections** against the 15 a full league
  needs. Both Scottish lower divisions price fully; the Premiership is patchy
  (3 of 5 unpriced), which is a bookmaker coverage fact, not a defect. The script
  needed repairing first — it still called the pre-Batch-14 `upcoming_saturday`
  and single-argument `fetch_slate(date)`, so it had been unrunnable since the
  slate window became per-league. Fixed in place; `.launch-private/` is
  gitignored, so that repair lives only on the owner's machine;
- ~~decide whether to enable the football-data provider~~ — **enabled, then
  switched back off on 2026-08-20**: `FOOTBALL_DATA_PROVIDER=none`. The
  `sync-football` run answered what the free plan carries — nothing after season
  2024. The provider question is now settled the other way: **FotMob replaces
  api-football** (ADR 0007, Batch 46), so this stays off until that adapter
  lands rather than until a paid plan is bought. `FOOTBALL_API_KEY` remains
  sealed and valid, and is irrelevant to FotMob;
- ~~rotate `ODDS_API_KEY`~~ — done by the owner on 2026-08-20, after the
  redaction shipped. `httpx` logged the full request URL at INFO and the key is a
  query parameter, so production had been printing it in cleartext on every odds
  call. Both halves are now closed and confirmed in production: `httpx` and
  `httpcore` are quieted to `WARNING`, and a live call with `httpx` forced back
  to `INFO` produced the key **0** times and `<redacted>` **1** time. The same
  call proved the rotated key valid — 63 UK competitions returned;
- ~~delete the `BF_*` variables from Railway production~~ — **done 2026-08-20.**
  All eight are gone from both production and staging. `variable delete` triggers
  no redeploy (verified on staging first), so production stayed on `88c4885c`
  throughout and all 13 required variables are intact. Reversible: every value is
  still in `.launch-private/`, and `seal-production-secrets.sh` re-seals them if
  `ODDS_PROVIDER=betfair` is ever selected again.

The `BF_*` variables and the Betfair certificate are no longer required in
production; they apply only if `ODDS_PROVIDER=betfair` is ever selected.

Build batches use `/batch-start <N>`, `/batch-verify <N>`, and
`/phase-closeout <N>`; launch phases use `/launch-start <L0-L5>`,
`/launch-verify <L0-L5>`, and explicit `/launch-closeout <L0-L5>`.

Both carried follow-ups are now closed. The `odds-api.io` key was rotated by the
owner on 2026-08-20 after the Batch 36 redaction shipped. The administrator PIN
is no longer the known bootstrap value: a login attempt with `roster.json`'s PIN
was refused against production on 2026-08-20, which is the evidence it was
changed. (That attempt incremented `failed_login_count` to 1 of 5 and it was
reset to 0 immediately — do not probe this by guessing, the lockout is durable
and locking the owner out before a Saturday is the worse failure.)

## Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`
