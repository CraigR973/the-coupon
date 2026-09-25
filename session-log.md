# The Coupon — session log

## Archive — `STATUS.md` as it stood on 2026-09-24

Batch 154 cut `STATUS.md` to a one-page current state. Everything it held before is
kept here verbatim, headings demoted one level, because parts of it appear nowhere else:
shipment records, owner decisions and production observations. **It is history, not
state** — much of it was already stale when it was moved, and where it disagrees with
`STATUS.md`, `STATUS.md` is right. The per-batch entries follow it, oldest first.

### Now

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
aggregate gap it left open — fifteen members at ten each exceeds the plan, and
fifty at ten is five times it — was closed by **Batch 89**: the submit path now
also charges a shared `50/hour;100/day` bucket keyed on the league, and a league
that has spent its share is refused with `PICKS_BUSY` rather than served a price
the provider did not confirm. The bucket bounds a league and not the
installation; what that leaves open is stated in a test.

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

Batches 73-77 closed the owner's 2026-08-25 list and its production follow-up.
**Batch 73** stopped a round
claiming to be open while it refused picks: `status` is only the label the hourly jobs
have caught up with, so the badge read Open both before a round's opening instant and
for up to an hour after its deadline. `pickRefusal` in `lib/coupon.ts` is now the
written-down rule, mirroring the API's own. The same defect was on the settings screen
twice over — its round list filtered on `status`, and its copy told admins a change
"never restamps a round that already exists", which Batch 40 wrote correctly and Batch
65 falsified. `PickShapeLine` also lost its longshot split and names its figure
`avg odds selected`. **Batch 74** is a script, not a change: 2-1 Hibs' four rounds
renumbered 1-4 and three members renamed, reversing a decision Batch 68 made
deliberately; it was applied and independently verified on 2026-08-26. **Batch 75** deleted a
nightly `pg_dump` that crossed the internet to write an uncompressed copy of a 12 MB
database into a `/tmp` no volume backed, keeping the same job runnable on demand.
**Batch 76** gave the product the notifications it never had — picks opening, somebody
claiming or moving, and one reminder three hours before the lock instead of one a day —
and closed the gap underneath them: `league_memberships.notification_muted` had existed
since Batch 32 with exactly one query honouring it, so `send_notification` could not
check a mute it was never told about. **Batch 77** made the opening trigger reachable
after a league adds a future opening to an already-discovered round: an unclaimed
`open` round moves back to `scheduled`, while a round holding a legitimate pick stays
`open` and records the declined transition at info level.

**Batch 78** is the first of the owner's three points of 2026-08-26 and the only
frontend-only one. `GameweekMember` and `CouponLeg` carry the same seven facts, so the
pick screen's roster and the combined coupon were two implementations of one list, and
they had drifted apart — only one marked the reader's own row. `PickRow` is now the row
both draw, taking a `lead` that says which fact is the heading: the roster asks who has
picked, the coupon asks what is riding on the week. The section's third tab was renamed
**Season**, because it was called Results and showed none — every row of it navigates to
the combined coupon, where Batch 67 put the scorelines and points. `GameweekNav` stopped
printing `pick_count/fixture_count`, a fraction of fixtures sitting beside the roster's
fraction of members with nothing distinguishing them.

**Batch 79** is the second of the three and the one with a finding under it. The home
card printed `Settled` and said nothing else about the week just gone. The result could
not be read off `current_round`, because `current_round_order` ranks a round accepting
picks above one already started and `accepting_picks` treats a NULL opening as open now:
on a league announcing no opening, next week's round displaces the settled one the moment
discovery writes it, so the member never sees their week — while the identical code works
on a league that announces one. `last_result` is its own read. Rank movement is
`standings_by_league` run twice with the reported round excluded rather than a snapshot
table, so movement and rank cannot come from different arithmetic. `GameweekResult` gained
`picks_won`, because `all_won` reads the same for five of six and none of six.

**Batch 80** closes the three. Every leaderboard figure was a season aggregate, so a
member who had won the last four rounds read the same as one who had scored nothing since
July. `Standing.recent_form` carries the last five settled rounds, sliced by
`row_number()` so a table's cost does not grow with the season. It is drawn by
`PickFormLine` and **not** by `FormLine`: a coupon pick has no drawn state, and letting a
void borrow the draw's pip would erase the `picks_played`/`picks_priced` distinction in
the place a reader would most likely believe it. Each round carries what it scored,
because points are `round(odds × 10)` and one win at 5.00 outscores two at 2.00.

**Batch 81** reversed one decision inside Batch 80 on the owner's call the same day. The
form run defaulted *off* and was deliberately absent from `PerLeagueSummary`; it is now on
by default and carried on the summary, so home draws it too. `with_form=False` survives
for exactly one caller — the table `routers/me.py` rewinds to difference two ranks, which
is never rendered — which is the right way round. The run sits inside Batch 79's result
panel rather than on the standings link, because `PickFormLine` is a `role="img"` whose
label would otherwise be appended to that link's accessible name.

**Batch 82** opens the 2026-08-26 review's work and is the only HIGH finding in it.
`POST /push/subscribe` stored whatever string it was handed as `endpoint`, and delivery
passes that straight to `pywebpush`, which POSTs to it from the server — so since Batch 63
opened self-registration, anyone could register, subscribe a destination of their choosing
and then trigger the send themselves via `/push/test`. Subscribe now requires `https`, an
allowlisted push-service host (FCM, Mozilla, Apple, or a `*.notify.windows.com` shard) and
no internal IP literal. The bypasses that matter are handled by reading
`urlsplit(...).hostname` rather than the raw string, which is what defeats
`https://fcm.googleapis.com@evil.example/`. **API-only, so it is not live until Group A's
`/ship-prod`.**

**Batch 83** made the display-name backstop match the check it backs up. `/auth/register`
compares names lowered — "Dave" and "dave" are one person twice in the standings — but
`uq_profiles_display_name` compared them raw, so two concurrent registrations for the two
spellings both read *not taken*, both satisfied the constraint, and both committed.
Migration **017** replaces it with a unique index on `lower(display_name)`, created before
the old constraint is dropped so no instant exists without a rule, and covering
soft-deleted rows exactly as the pre-check does. **It refuses to run on a database that
already holds a collision, and names the rows** — this runs on boot, and it could not be
checked against production first: that host is IPv6-only with no route from the
workstation, and the project's REST API is 402 under the egress quota. `/ship-prod` is
where 017 first meets real data.

**Batch 84** shut a league window out of the hour the clocks change. Every local instant
a window produces is `datetime(y, m, d, tzinfo=UK_TZ) + timedelta(minutes=...)` — wall-clock
arithmetic — so on the last Sunday of March 01:00-02:00 does not exist, on the last Sunday
of October it happens twice, and Python resolved both silently through `fold=0`. Since Batch
63 any member can create a league, so any member could configure one. `create_league` and
`update_league` now answer 422 and name which of the four instants is at fault — opening,
close, lock, or announced opening, each built by the same arithmetic. The check sits in the
handlers rather than the request schemas because a PATCH naming only a minute is judged
against the weekday already stored. Transition days are read from `zoneinfo`, not assumed.
The default Saturday 15:00 window is unaffected, and validation is on write only, so no
existing league is re-judged.

**Batch 85** closed the last gap in Batch 76's work. `notify_member_joined` was the one
trigger of the four that never passed `league_id` into `send_notification`, so the
per-league mute had nothing to check and a site admin who had muted a league still got its
"New member" push — a message that names that league in both its title and its body. The
parameter is required rather than defaulted, so a fourth call site cannot reintroduce the
omission silently.

**Batch 86** gave `/login` and `/register` the landmark and heading every other screen
already had. They are the only two rendered outside `Layout`/`ProtectedRoute`, so they
inherited neither the `<main>` `Layout` provides nor the `<h1>` `PageHeader` gives each
authenticated page — 26 axe nodes across three rules, in both themes. The page shell is now
the `<main>` and the card title is the `<h1>`, carrying `CardTitle`'s own classes so the
rendered type is identical; `CardTitle` itself is shared and untouched. **Web-only, so it is
live on Vercel from this push.** Nothing on either screen looks different — the change is
what a screen reader and keyboard landmark navigation get. Two of the three rules cannot be
verified under jsdom at all (axe needs layout to decide them, and returns "incomplete" for
correct and broken markup alike), so they are checked in a real browser by the new
`e2e/prod-bundle-a11y.spec.ts` inside ci-local's existing prod-bundle step.

**Batch 88** closed an open redirect on the two public screens. `?next=` is read straight
off a URL anyone can send, and the guard on both pages tested `startsWith('/') &&
!startsWith('//')` — which stops `//evil.com` but not `/\evil.com`, since that starts with
a single slash and browsers read `\` as `/` inside a special scheme. The review rated the
mechanism plausible-but-unconfirmed; it is confirmed now, in Chromium, against the built
bundle: the old predicate accepted all three backslash forms and every one resolved to
`http://evil.com/`. A member signing in from such a link would have arrived on another host
with tokens already in localStorage. The guard now lives once in `lib/redirect.ts`, resolves
the value through the browser's own URL parser and keeps it only if the origin held, and
returns the parsed path so react-router cannot land somewhere other than what was checked.
**Web-only, live from this push.** Nothing looks different; invite links still carry members
to `/join/:token` as before. react-router 7 (Batch 102) is the complete upstream fix and is
now unblocked, but this guard stands independently of it.

**Batch 87** stopped the service worker keeping data the API told it not to keep. The
`/api/v1/*` route cached on HTTP status alone, so every authenticated read sat in Cache
Storage for up to an hour even though every API response is marked `Cache-Control:
no-store`. Logout cleared it, but a merely *locked* device — access token expired, refresh
token still there — held the previous reader's league data where any page-context script
could read it without a bearer token, Cache Storage being same-origin-scoped rather than
permission-scoped. The route now drops any response carrying the directive. **Web-only,
live from this push.** The visible consequence is that API reads no longer survive going
offline: a flaky connection reaches the offline banner instead of a stale league table,
which is the trade the review asked for. Note the review's alternative suggestion — drop
`CacheableResponsePlugin` and rely on the in-flight fallback — would have cached *more*,
not less: `NetworkFirst` persists by default and that plugin only narrowed it.

**Batch 89** bounded pick submission in aggregate, not only per member.
`PICK_SUBMIT_LIMIT = 10/hour` caps one member; at `max_members`'s real ceiling of fifty
that is `500/hour` against a `100/hour` provider plan, and exhausting it is silent —
everybody's prices simply stop refreshing. `POST .../picks` now also charges a shared
`50/hour;100/day` bucket keyed on the league, and a league that has spent its share is
refused with `429 PICKS_BUSY` rather than served a price the provider did not confirm.
Fifty is deliberately both what the hour leaves after peak browsing and `max_members`
itself, so a full league can still take one pick each. **Shipped 2026-08-28** (`359c08f1`, Railway
`9cc1ef2a-a108-4066-84c1-a1626a1b0c71`). The bucket bounds a league
and not the installation; two concurrent full-tilt leagues put the plan back in charge,
and that residual is stated in `test_request_budget.py`.

**Batch 90** gave that write real resilience. `usePickEditor` was a bare mutation with no
retry, no offline detection and no deadline, so "the wifi dropped" and "someone beat you
to Arsenal" arrived as the same sentence and a member could not tell whether their claim
had landed. `apiFetch` now separates a request that was never started (`navigator.onLine`
false — it definitely did not land) from one that left and went unanswered. A pick of the
first kind is **queued** and sent on reconnect; one of the second is **unconfirmed** and
is never re-sent on its own — reconnecting reads the round's pick back instead, because
re-sending would silently take the claim of a member who has since changed their mind
backwards. `OutstandingPickNotice` keeps that state on screen with the matching action,
and the queue is in memory only: an unsent intent that outlived a sign-out would fire
under whoever holds the phone next. Web-only, live from its own push; the
`PICKS_BUSY` copy it carries was unreachable until Batch 89 shipped a few minutes later,
which is why Group C was cut to ship at its boundary.

**Batch 99** stopped a redeploy handing every rate limiter a fresh bucket. Every counter
in the app lived in process memory, so a Railway restart — several a week here — reset
`/auth/login`'s `5/15 minutes` and `/auth/pin/reset-request`'s `3/hour` along with
everything else; five guesses, wait for a deploy, five more. Those two now charge a
Postgres table (`rate_limit_counters`, migration **018**), one row per live bucket rolled
forward in place. The provider budgets — `PICK_SUBMIT_SHARED_LIMIT`,
`PROVIDER_SLATE_FETCH_LIMIT`, `PICK_SUBMIT_LIMIT` — deliberately stay in memory, where a
reset costs provider requests rather than protection, and tests fail if either half of
that split moves. The counter runs on its own session, so a login for a name that does not
exist is still charged even though the handler commits nothing; the 429 body is byte-for-
byte what it was, because `AuthContext.tsx` branches on `{"error": ...}`. API-only, so it
is **not live until `/ship-prod`**.

**Batch 100** turned the single-replica precondition from a note into a check that runs.
`nixpacks.toml` starts the service with `alembic upgrade head && uvicorn ...`, which is
correct only because `.railway/railway.ts` pins one replica; raise it and two containers apply
the same DDL to the same database seconds apart, with Alembic holding no lock of its own.
`src.migration_guard.assert_single_replica` now runs from `migrations/env.py` before the
engine is built, so it covers every way an upgrade is invoked and not just the start
command. The count is baked into the image as `DEPLOY_REPLICA_COUNT` and a test holds it
equal to what `.railway/railway.ts` actually asks for — summed across `multiRegionConfig`,
because two regions at one replica each is two processes while `numReplicas` still reads
`1`. Above one it refuses, names the count, says the database was not touched and points
at the release-step alternative set aside on 2026-08-27. API/infra only, **not live until
`/ship-prod`**.

**Batch 101** gave the FotMob dependency a definition of "this has bitten". Its terms
prohibit automated access; the owner took that knowingly and it stays revisitable, but
three shipped features rest on it — Football Stats, the void-fixture cross-check before
lock, live in-play scores — and TheSportsDB was named as the fallback with nothing
tracking when to reach for it. Now: `401`/`403`/`451` alert on the first one, because the
terms being applied do not un-apply; any other failure needs five in a row with no success
between, so an ordinary timeout says nothing; and a slate where *nothing* could be
cross-checked alerts immediately and loudest, because that is the one FotMob dependency
that decides whether a member's pick is valid. Alerts write an `audit_log` row
(`football_provider_degraded`, migration **019**) and push site admins, with a cooldown
read from those rows so a ten-minute job cannot push every ten minutes and a redeploy
cannot restart the noise. No TheSportsDB adapter — set aside as a separate call. API-only,
**not live until `/ship-prod`**.

**Batch 102** moved the router off the advisory-stranded 6.x line. Both
`react-router-dom` and `react-router` now resolve to **7.18.3**, removing
`@remix-run/router` and clearing the two React Router findings that otherwise required a
fresh reachability analysis on every dependency scan. The app is declarative routing
only — no loaders, actions, fetchers or data router — so v7 required no source rewrite;
the existing `react-router-dom` imports remain supported and Batch 88's app-owned
`?next=` guard stays in place. Its hostile redirect suites pass 56/56 and the production
bundle deep-link smoke passes. Web-only, so it creates no `/ship-prod` obligation.

**Batch 91** opened Group E by making a new league invite-only unless its creator says
otherwise. `CreateLeaguePage` had initialised `privacy` to `public_open`, and since Batch
63 opened self-registration that no longer means "people the creator already knows" — it
means anyone who has signed up. The API had defaulted to `private` all along
(`CreateLeagueRequest.privacy`), so the form was overriding a server default that was
already right; this closes the divergence rather than setting a new policy, and needed no
API change. Each option now names its consequence and carries a help line, tied to the
field with `aria-describedby`, that changes with the selection — and the copy is taken
from the router rather than the option names: `private` is absent from `/discover` and
refuses slug joins with `PRIVATE_LEAGUE`, but the **join code still admits anyone holding
it**, which is why the text promises "only people you send the join code to" and not
invite-only as a security claim. No existing league moved; production's `test` league
stays `public_open`. `LeagueSettingsPage` keeps the unexplained dropdown, where the stakes
are higher — switching to `public_open` auto-approves every pending join request and
switching to `private` cancels them, silently — and that is left for its own batch.

**Batch 93** told the three members Batch 74 renamed. Their sign-in name changed on
2026-08-26 and nobody was signed out — the JWT subject is the player id — so the surprise
was waiting for the next session expiry or forgotten-PIN request, days later and looking
unrelated. The batch turned up a fact worth keeping: **this product has no in-app
notification inbox at all** — no model, no screen, no route — so "notify a member" means
web push and nothing else, and a member without an active subscription cannot be reached.
That is why the notice runs from `lifespan` rather than a migration (a migration cannot
make an HTTP call per subscription), why its once-only guarantee is an `audit_log` row
rather than Alembic's version table, and why the marker is written **only when a push
actually landed** — a muted or unsubscribed member has not been told, so the next boot
tries again rather than marking them done. Migration **020** adds the
`display_name_changed` action type that marker needs. A `pg_advisory_xact_lock` serialises
the task, because Batch 100's single-replica guard covers migrations and a lifespan hook is
not one. API-only, **not live until `/ship-prod`**.

**Batch 94** gave a league admin the trail of their own league. `audit_log` rows have been
written for league-level actions since Batch 1 and the only reader in the API was the
site-admin dashboard — 25 rows, flat, global across the whole deployment — so the person
who most needs to know who changed the fixture window or removed a member, usually the
friend who set the league up rather than the site operator, had no way to find out.
`GET /api/v1/leagues/{slug}/audit-log` behind `LeagueAdminDep`, paginated at 25 a page, with
a page at `/leagues/:slug/admin/audit-log` reachable from the Manage menu as **Activity**.
The scoping is the substance: **`audit_log` has no `league_id` column**, and the batch was
not allowed to change what the writers record, so the association is reconstructed — and
the writers disagree. Nearly all of them pass `target_id = league.id` even when
`target_table` names another table, but `league_invite_revoked` records the invite id and a
league-scoped PIN reset records the player id, naming the league in `changes.league_slug`
instead. A `target_id`-only filter would have looked right and silently dropped every
revoked invite and admin-performed PIN reset, which is worse than no screen; the second arm
catches them, and a cross-league test plants a foreign league's slug to prove the arm does
not leak. The response carries `changes`, which the site dashboard drops, because "a member
was removed" is not the answer — "who removed whom" is.

**Batch 96** gave standings a season. `standings_by_league` aggregated every settled pick a
league had ever played while its own docstring called the result "Season tables", so a
league in its third year read as one table three years long and no season could ever be
won. The boundary is `season_bounds` over `season_for` — the definition round numbering
already uses — rather than a second one, so a round cannot belong to one season for its
number and another for the leaderboard. `season` defaults to the one being played, and any
other season is the archive read through the *same* ranking rule, which is why it is a
parameter rather than a stored snapshot: there is still exactly one way to rank a league.
The substance is where the filter sits. It is in the **join** to `picks`, beside
`exclude_gameweek_ids`, because as a `WHERE` it would drop a member who has not played this
season out of the table rather than showing them on nought — a leaderboard quietly missing
a player reads as a membership bug, not as a season having started. `recent_form` stops at
the boundary too, or a member two rounds into a season would get five pips with three of
them describing a season their total no longer counts. `routers/me.py` passes the same
season to both of the tables it differences for "you moved up two", and now leaves
`rank_movement` unset when the round being reported is not in the season the table covers.
`GET /leagues/{slug}/seasons` is the archive index and the leaderboard grew a season strip
addressable as `?season=`, hidden below two seasons. **No migration** — the boundary is a
query-level filter and production stays at revision **020**. API and web both, **not fully
live until `/ship-prod`**; until then the strip is hidden, because `/seasons` 404s.

**Batch 98** replaced avatar tints with solid colour. The old component painted raw fill
tokens as text over 15%-mixed versions of the same colours; bronze measured 4.05:1 and only
two of the six name-hash slots had ever appeared in the review seed. The palette now pairs
each solid fill with near-black or white initials, switching the foreground by theme only
for metal and bronze where the arithmetic requires it. The shipped token pairs are data in
the component and the contrast suite measures all twelve slot/theme combinations against
the same metadata, with light bronze the floor at **4.93:1**. `tintFor()`'s hash and palette
order did not move, so every member keeps the same colour slot. The real-browser coupon flow
now runs axe's `color-contrast` rule on settled standings at 390×844 in both themes and saves
both screenshots; both sweeps report zero violations. Web-only, so no `/ship-prod` is owed.

**Batch 97** gave home the altitude it was missing. Its row predated Batches 79 and 81, so
the example content — every league, each opening/lock countdown, and recent activity — was
already on the page by the time the visual pass began. The one response also carried
aggregate season figures that home discarded. A new 218px cross-league hero now answers
which independent league needs the member next, sorting actionable leagues by their own
lock rather than the API's alphabetical order, and links straight to that coupon. With no
pick outstanding it says whether all open picks are in and names the earliest announced
opening. Points, picks won/played and win rate form the season pulse; average rank stays out
because it is not meaningful across leagues without its coverage caveat. The scale half is
real rather than a spacer: 32px greeting, larger action line, roomier league cards and result
panels, an explicit leagues section and wider vertical rhythm. In the sparse one-league
settled case content now lands immediately above the tab bar at 390×844 in both themes;
axe reports zero violations. Web-only, using the existing summary route, so no
`/ship-prod` is owed.

**Batch 92** made the two post-play moments pasteable. A settled combined coupon no longer
copies the pre-lock betting payload: its plain text says how many picks landed, preserves
the frozen-price context and numbered leg format, and adds each available final score,
status and points without inventing nil-nil when the result join has no score. The same
clipboard mechanism now copies the standings table on screen, naming its league and exact
selected season and serialising only those displayed rows; an archived table therefore
cannot silently turn into an all-time or current-season share. The pre-lock builder remains
byte-for-byte covered. Both controls passed a full axe sweep and visual inspection at
390×844 in dark and light. Web-only, so no `/ship-prod` is owed.

**Batch 103** gives the settings privacy control the consequence copy the create screen
already had and makes both read one shared option table without changing the shorter
`PRIVACY_LABELS` used elsewhere. The settings form now has no permissive fallback while its
league is loading. Before a `public_request` league becomes open, it names how many pending
requests will be auto-approved; before a changed league becomes private, it names how many
will be cancelled. Declining either confirmation prevents the PATCH, and a consequential
transition fails closed until the existing admin join-request query has loaded. Web-only,
so no `/ship-prod` is owed.

Batches 1-94 and 96-103 are closed. The Coupon is a
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

### Verified

- Backend: the complete PostgreSQL-backed pytest suite, Ruff check/format, and
  strict mypy; Batches 91 and 93 each passed `scripts/ci-local.sh` end-to-end
  (11 checks) green on the first run, as every close-out since Batch 26
  has. That script's pinned venv **is**
  the gate: app-starter's venv can no longer even collect the suite (no Pillow, so
  `avatar_storage.py` takes ten test files down with it) and `AGENTS.md` plus
  `docs/agent-commands/batch-verify.md` still document that stale path
- Database: clean `pgserver` migration through revision `020` (production is at `020`), including a pre-009 backfill, a 009 downgrade round-trip, and a 010 up/down round-trip, with forced RLS
  on all 18 public tables under a Supabase-like role setup. The count was 13 at
  revision `004`; `009`-`013` added the rest, and every one of the 18 was
  confirmed RLS-enabled *and* forced against production on 2026-08-19, with
  `anon`, `authenticated` and `PUBLIC` holding no table privileges and no schema
  `USAGE`
- Frontend: Node 20 production build, TypeScript, ESLint, and 715 Vitest, the
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

### Next

**Group N has shipped.** `scripts/check-deploy-drift.sh` reports the deployed API in sync
at `89217f82`, migration 025, so Batches 120, 121 and 122 are live and no `/ship-prod` is
owed for them. The nine-phase run order in `docs/review/2026-09-13/09-prompts.md` is the
running order from here; Phase 3 (158, 137, 138, 139, 167) is under way. Batch 95 remains
soft-blocked and Batch 115 is superseded by 119, so neither is the next implementation.
The production calendar backfill remains a separate explicit owner action; do not infer
authority to run it from a batch or deployment command.

**Batch 152 hardened the automatic delivery gate** (`5cefff3`). The local gate now records
and enforces exactly 1,179 PostgreSQL-backed backend tests and 1,045 frontend tests, with
zero skips; those baselines may only move upwards. Ordinary batches cannot alter the gate,
CI workflow, test discovery, or lint/type configuration while being judged by them. The
production-bundle smoke owns strict port 4173 and waits for its own Vite process to become
ready. Close-out checks deployment drift before the push and refuses an API+web batch until
the owner explicitly schedules `/ship-prod`.

**Batch 120 closed the simultaneous-claim failure** (`c822e69`). Both selection-scoped and
fixture-scoped leagues now preserve the intended conflict code before a losing transaction
rolls back, so every loser receives 409 with CORS rather than an uncaught expired-object
reload producing 500. The real-PostgreSQL regression puts ten members through the database
race in each scope and proves one winner, nine documented conflicts and one stored pick.

**Batch 121 closed the same-week stray-round score** (`be387da`). Retirement now inspects
through the football week's following Tuesday, so a Saturday left behind by a move to
Friday is removed before it can be claimed. If a pre-existing claim makes an undeclared
stray non-retirable, settlement refuses it and writes an operational error instead of
awarding points. Declared global calendar extras remain intentional second rounds and
still settle; they are distinguished from strays by the stored season calendar.

**Batch 122 closed the league-admin PIN-reset takeover** (`30fe08b`). The league-scoped
reset now refuses a target who is a site admin or an active admin of any league, using one
403 contract that directs privileged recovery to the site console without disclosing which
role triggered it. Ordinary-member recovery, session revocation, the 24-hour claim window
and the site-console reset are unchanged.

**Batch 158 made keyboard focus visible** (`fa922f8`). `--shadow-glow` was a ring at 20-25%
alpha, so the focus indicator on every button measured 1.49-1.53:1 in dark and 1.27-1.28:1
in light against the 3:1 WCAG 2.2 requires — and axe has no focus-indicator rule, so 88
clean automated runs never mentioned it. The ring is now two solid layers: a 2px `--surface`
gap that keeps it off the control's own fill, then a 3px ring in the `-ink` half of the same
brand token, which `contrast.test.ts` already holds to 4.5:1 on all four surface tiers in
both palettes. A third token, `--shadow-glow-on-brand`, serves controls sitting on a brand
fill. The two hold-outs that styled focus with a bare `ring-*` utility now use the shared
tokens and a test refuses any new one. Web-only; live on the close-out push.

**Batch 137 put every public screen in a landmark** (`8ed2740`). `/forgot-pin`, `/set-pin`,
`/join/:token` and `/welcome` had no `<main>`, no level-one heading and all their content
outside any landmark — the defect Batch 86 fixed for `/login` and `/register` and explicitly
scoped to those two. `CardTitle` now takes an `as` prop so a public page can title at `<h1>`
without a fifth hand-rolled copy of its class string. `BrowserOnboarding` claims the landmark
only on the two routes where it *is* the page; as `InstallPromptController`'s overlay it stays
a `<div>`, because the route underneath already has a `<main>`. Both accessibility sweeps now
enumerate every public route rather than a sample. Web-only; live on the close-out push.

**Batch 138 stopped dimming tuned text with opacity** (`6794111`). `opacity-70` composites
an element into its backdrop rather than dimming its colour, so text tuned to exactly AA fell
under: the team-season kick-off time at 2.83:1 in light, the season strip's "now" badge at
3.57:1. Each now steps down a token — primary, secondary, muted — instead of fading. Measuring
the grounds found the larger half the review had not: the strip's **selected** chip is
`bg-primary/15` inside a `bg-surface-elevated/70` panel, and brand ink on that composite is
3.87:1 in light with no opacity involved, so the chip's own label was failing too; the
results-day carousel is 3.95:1 the same way. Both selected chips now use `--text-primary` and
keep their brand cue in the border and tint. `contrast.test.ts` now measures composited
grounds, which no assertion in it previously did. Web-only; live on the close-out push.

**Batch 139 opened the round on a fixture and gave refusals their own tone** (`7d0e56b`).
Every competition group used to start collapsed, so the round screen arrived as headings and
counts with no fixture and no price; the first group now opens and the rest stay shut.
`defaultOpen` seeds state only, so closing it sticks across a refetch. Separately the app had
57 error toasts, 44 success, two informational and zero warnings — a lost race, a moved price,
the league's provider budget running out, a genuine failure and a queued offline pick all
looked the same. `pickRefusal` now returns a tone plus the single step that follows: lost races
and moved prices are warnings carrying "Refresh the card" and "Take <price>", a queued offline
pick is informational, and anything that genuinely failed stays red with no button on it.
Web-only; live on the close-out push.

**Batch 167 closed Phase 3 with three defects axe cannot see** (`597905d`). Pick-market
labels carried an unqualified `truncate` and were cut off at 320 CSS px, where two-up
selections leave about 68px for a label wanting 106; they now wrap below `sm`. Closing the
bottom-nav "More" sheet with Escape left focus on `<body>` because Radix restores focus to a
`Dialog.Trigger` and this sheet is driven by `open` instead — `Sheet` now takes an optional
`triggerRef`. And sonner publishes every toast through one polite live region with no
per-toast override, so `AppToaster` switches sonner's off and carries the text in two of its
own: assertive for errors and warnings, polite for the rest. `e2e/prod-bundle-reflow.spec.ts`
is the first check in the suite to measure 320px reflow or the WCAG 1.4.12 text-spacing
override, over every route the prod-bundle harness can reach. Web-only; live on the push.

**Batch 123 stopped a griefing lock costing a member their session** (`37c6e40`). The
account lock is unchanged — admitting a correct PIN during one would reopen unlimited
guessing — but a cold start now spends the stored thirty-day refresh token before asking
for a PIN, so a member who has already proved who they are is let in without touching the
path a rival can close by spending five attempts a quarter of an hour. `refreshStoredSession`
leaves storage intact on failure, because the PIN screen is the fallback and needs the stored
player; while the request is in flight the app says it is resuming rather than flashing a PIN
prompt. Unlock failures are now mapped from the status instead of all reading "Invalid PIN",
which had been sending members to reset a credential that works. On the API,
`LOGIN_SOURCE_FAILURE_LIMIT` bounds one *source* to fifteen wrong PINs a quarter of an hour —
charged after the PIN check, so a correct sign-in from a shared address costs nothing — and a
member whose account locks is told once per lock. Shipped to production on 2026-09-23 as
`f5136b1b`; Railway `f4a2b87b` → `1ead8cc4`, Vercel section a no-op on
`dpl_7tPV4tkCGcSmH9ReofZfeUBXr1hK`.

**Batch 124 stopped the join code walking past removal and approval** (`da8a13d`). Removal
never rotated the code and `_upsert_membership` restores a soft-deleted row, so a removed
member who pasted the code back was in again immediately; removal now rotates it and writes
the existing `league_join_code_rotated` audit row. Separately a `public_request` league was
gated at one door only — `/join` opened a request while join-by-code created the membership —
so both now go through one extracted `_create_join_request`, and `JoinByCodeResponse` gains
`status` ("joined" / "pending") to match what `/join` already answers. The two web callers of
join-by-code no longer navigate into a league on a `pending` answer; they say a request was
sent. **API + web: `/ship-prod` is owed.**

**Batch 125 made oversight a read rather than a licence to play** (`623f9b7`). The
league-membership dependency let site admins past the check for writes as well as reads, so
a site admin who had never joined could submit a pick — which consumes a selection from that
league's pool and takes it from a genuine member, while the admin appears in no member list
or standing and has no membership to leave. The bypass is kept for reads; writes go through a
second dependency with no bypass, used by `submit_pick` and the per-league display-name
override. A structural test walks every route and fails any mutating one that still depends on
the read variant. **API-only: `/ship-prod` is owed.**

**Batch 126 made a member's name theirs within a league** (`ae187ea`). The per-league
display-name override stored whatever it was sent, bounded only by the column's 100
characters — no charset, no normalisation, no uniqueness — while the roster, standings and
coupon all render it, so two members could appear under one name. The registration rules move
to `src/display_name.py` and both paths now read them from there; uniqueness is on the
*effective* name (override, else profile name) within one league, case-insensitively and after
normalisation, excluding the caller. Clearing is deliberately unchecked, so a pre-existing
clash cannot trap someone with an override they cannot remove. **API-only: `/ship-prod` is
owed, together with Batch 125.**

**Batch 141 gave the web app a Content-Security-Policy** (`591d0c2`). It shipped four
headers and no CSP, no `frame-ancestors` and no `X-Frame-Options`, which matters because the
client holds a thirty-day refresh token in `localStorage`. The policy is `default-src 'self'`
with `frame-ancestors 'none'`, `object-src 'none'`, `base-uri`/`form-action` locked to self,
and a `connect-src` naming both API origins rather than allowing https wholesale. `script-src`
is `'self'` plus a single hash for index.html's pre-mount theme script, recomputed by a unit
test so the two cannot drift; `style-src` keeps `'unsafe-inline'` because Radix, sonner and
framer-motion inject styles at runtime. A new prod-bundle spec applies the shipped policy to
`vite preview` — which does not read `vercel.json` — and loads every public route under it,
with the service worker and the preloaded font asserted by name. Web-only; live on the push.

**Batch 143 made logout forget the league** (`5c02dcd`). `clearTokens()` removed the token
keys only, so a private league's slug and name survived a logout on a shared browser and
pre-selected for whoever signed in next; both league keys now go on logout and on an identity
switch. `forgetLeagueContext` lives beside the keys it clears, and the switcher's scroll key
moved into that module so `lib/` never imports a component. Separately `claim-invite` looked
its league up without the `deleted_at` filter every other lookup applies, so an invite to a
deleted league resolved and built a membership of a league that no longer exists; it now
refuses cleanly. **API + web: `/ship-prod` is owed.**

**Batch 159 narrowed the match-day refresh** (`d1d4b60`). `run_refresh_slate` called
discovery with no competition list, so it walked the full pool — 41 competitions where the
daily job walks about 20 — and a walk costs `windows x dates x competitions` at one `/events`
request each. Two windows was 82 requests in one hour, twice a day, against a 100/hour plan; a
third window took the hour to 145 and the day to 527. It now narrows exactly as the daily run
does, with the same empty-pool release so a fresh deployment can still bootstrap. The saving is
measured against a counting provider driving the real job, not asserted from the argument.
**API-only: `/ship-prod` is owed.**

**Batch 160 made the plan counter honest** (`8b1aa0d`). It was charged only from the odds
cache's own refills, so `fetch_slate`, `fetch_competitions` and `settle` never reached it and
the gauge saw roughly 127 of a Saturday's 283 requests — while the cache's widening valve and
the 50-request pick reserve both read that gauge. `OddsApiProvider` now counts at the single
HTTP chokepoint all its requests pass through, and the cache charges the delta across each
forwarded call, so retries, the memoised catalogue fetch and a call that raised are all
recorded. `fetch_odds` is untouched, and no tier, threshold or reserve size moved.
**API-only: `/ship-prod` is owed, with Batch 159.**

**Batch 161 bounded the pick path by what the deployment has left** (`39b299f`). The pick
path charged a per-league bucket of 50/hour against a 100/hour plan, so five leagues was
250/hour and twenty was 1,000/hour — real spend, because the refusal path exempts the pick
path. A second bucket now sits beneath the per-league one, keyed on the deployment, with the
same numbers: they were always a statement about the installation that happened to be keyed
per league. **It inverts a property an existing test asserted** — a quiet league no longer
picks through a busy one's exhaustion — because the plan leaves about fifty pick requests an
hour and two leagues cannot both have fifty. `PICKS_BUSY` and the per-league limit are
untouched. **API-only: `/ship-prod` is owed, with 159 and 160.**

**Batch 133 gave discovery a budget and made it spend it across windows** (`a498e2a`). The
run costs `windows x dates x competitions` and only the last factor was bounded, so a third
distinct window — a league-settings change, not a deploy — put it near 120 requests against a
100/hour plan and would have 429'd partway. `discovery_request_budget` (90) stops the run
cleanly with everything already bought committed, and the walk is now interleaved by date rank
rather than window by window: a shortfall costs the far end of every window's horizon instead
of the whole of the last window. **API-only: `/ship-prod` is owed, with 159, 160 and 161.**

**Batch 162 answered the member before telling the league** (`c36beb4`). `notify_pick_made`
ran 49 sequential sends taking 8,759 ms on a fifty-member league — about 1.7 seconds at
production's twelve — on the submitting member's own request. Both fan-outs now run in a
Starlette background task on a session of their own, after the response body has gone;
`record_completion` stays on the request path because it is the durable write Batch 107's
retry depends on. **API-only: `/ship-prod` is owed, with 159, 160, 161 and 133.**

**Batch 129 routed the discovery-silence alarm to the push channel** (`2179fb5`). Batch 119
built the two reads that would have caught a week of silent scheduling, then sent them to the
dashboard and the logs — both of which need somebody to look. They now push to site admins,
naming the leagues with members and nothing to play. The cooldown is a durable rate-limit
counter rather than an audit row, so it survives a redeploy without needing a new `ActionType`
and the migration that would have required. **API-only: `/ship-prod` is owed, with 159, 160,
161, 133 and 162.**

**Batch 147 stopped the pick reminder losing the fall-back hour** (`665e266`). On an hourly
Europe/London cron the October fall-back skips an hour — 23:15 UTC straight to 01:15 UTC —
and a reminder cannot recover from that the way a lock sweep can, so a round locking roughly
03:15-04:15 UTC on 25 October was never reminded. The trigger is now UTC, alone among the
domain jobs; `gameweeks_due_a_reminder` already selected on the UTC lock instant, so the wall
clock was never load-bearing. **API-only: `/ship-prod` is owed — this completes Phase 5.**

**Batch 130 completes a round when the roster change fills it** (`092ff38`). A round
completes when every *active* member has picked, and only the picking path recorded that — so
a round filled by the last outstanding picker leaving, being removed or being deleted
announced nothing, and a later unrelated pick change fired the event and credited that member.
All three doors now re-evaluate completion and attribute it to the transition rather than to a
member. The new line is keyed on the empty picker **name**, not a null id: the id has been
nullable since long before this because the foreign key is `ON DELETE SET NULL`.
**API-only: `/ship-prod` is owed.**

**Batch 131 divided win rate by the picks that actually ran** (`8eff2bb`). It divided by
`picks_played`, which includes void, so a void lowered a win rate exactly like a loss — a
void-only member read 0%, and three wins plus a loss plus a postponement read 60% where the
record is 75%. It now divides by `picks_priced`, the same reasoning `scoring.py` already
applies to the odds denominator. A member with no priced picks has **no** win rate: `None`,
which every surface already renders as an absent statistic — not 0% and not 100%.
**The oracle test changed**, which `AGENTS.md` makes a decision rather than a batch's own
call; the owner took it on 2026-09-23 and both the old and new expressions are in the file.
**API-only: `/ship-prod` is owed, with Batch 130.**

**Batch 132 guarded the two calendar rules a declaration can break** (`efdfdeb`).
`declare_extra_week` had no past-date and no settled check, so declaring a past Wednesday
renamed an already settled, already picked round from "5" to "5b"; it now refuses both,
mirroring `move_anchor` and `withdraw_extra_week` — the settled lock narrowed to the one
football week a declaration can relabel. Separately the season anchor was whichever round
discovery happened to write first, so a Friday league walked before a Saturday league split
week 1 into "1" and "1b"; `reanchor_from_earliest_round` now pulls it back to the earliest
canonical Saturday the season holds, earlier only and only while nothing has settled.
**API-only: `/ship-prod` is owed, with 130 and 131.**

**Batch 156 left voided legs out of the combined coupon** (`46b8d29`). `build_coupon`
multiplied every frozen price into the accumulator unconditionally — production showed
`53.01 = 3.75 x 1.90 x 3.10(void) x 2.40`. A real accumulator settles a voided leg at 1.0,
and the product's own rule is that a void scores nothing rather than counting as a loss. The
leg stays on the coupon with its price; only the product changes, and `void_leg_count` (new,
optional) lets the screen and the clipboard both say why the fold is smaller than the legs.
**API + web: `/ship-prod` is owed.**

**Phase 7 shipped on 2026-09-24** (`13431987`, Railway `8701d8c3-…`, **migration `026`**),
carrying Batches 144, 145, 146 and 128. Drift reports in sync and both health endpoints agree
at `026`. Two things were not confirmed and are not assumed: the direct-database RLS/grant
recheck (the Supabase host is IPv6-only and this machine lost IPv6 mid-shipment), and Batch
145's compression in production (no public response is over the 4 KB floor). A first attempt
an hour earlier was refused by Railway at `SNAPSHOT_CODE` and shipped nothing.

**Batch 155 took members' names out of the public repository** (`ca62213`, 2026-09-24).
The review flagged two renamed members; re-verification found eleven — nine more
first-and-surname display names sat beside their picks in the Batch 68 backfill. Every
non-owner member is now "Member A" to "Member L" in code, tests and documents (owner
decision 2026-09-24); git history still holds the names, since no rewrite was authorised.
The boot-time rename notice now finds its three profiles by id and says the old sign-in
name has gone rather than quoting it. Production, read 2026-09-24: the owner and member A
are marked told; member B has no push subscription and has not been told (Batch 148).
**API-carrying: `/ship-prod` is owed** for the notice to switch.

**Batch 166 is parked, unstarted.** Its verification requires a Lighthouse mobile run on the
standings screen — behind authentication, on a real league — before any change is made. A
local stand-in measured 2026-09-24 (same bundle, seeded league, Chromium at 4x CPU throttle)
puts median total blocking time at **109 ms** with the main thread 58–70% idle, which is
supporting evidence that the 915 ms has gone but **not comparable** to a Lighthouse figure.
The largest named application cost in three profiles is `useSlidingIndicator`, Batch 164's
own tab-indicator hook, at 20–26 ms.

**Batch 165 stopped the countdown re-rendering the screen, and named the cache keys**
(`13e49b4`). The tick lives in a memoised `<Countdown>`; the pages use `useExpiry`, one
timeout to the boundary. Both context values are memoised. **A live bug came out of the third
part:** leaving a league invalidated `['leaderboard', slug]`, a key no query has — it cleared
nothing and left the member on the table of a league they had left. `lib/queryKeys.ts` now
owns every key. **Web-only.**

**Batch 164 replaced framer-motion with CSS** (`7e37b9b`). 107 KB of JavaScript for five
transitions, 62% unused on home; the 109 KiB chunk is gone and the precache drops from 917.2
to 785.7 KiB. **One behaviour changed:** route transitions no longer animate the outgoing
page away first, so a change is 220ms rather than 440ms. Reduced motion is now one CSS rule
instead of a hook `TabBar` never called. JetBrains Mono 700, which nothing used, is gone too.
The dependency stays in `package.json` (protected file); nothing imports it and a test holds
that. **Web-only.**

**Batch 163 stopped precaching the admin consoles** (`ba3f580`). The service worker
downloaded all 82 emitted files on install, undoing the route splitting; it now precaches
917.2 KiB instead of 979.0 and leaves 13 admin chunks to load on demand. Two admin pages had
to be renamed first — they emitted the same chunk basenames as the member-facing Dashboard
and Results, so a prefix filter would have stopped precaching home. **Web-only.**

**Batch 146 indexed the two reads that sweep rounds** (`ee3d196`, **migration `026`**).
`gameweeks.starts_on` had no index and `picks` had none a `gameweek_id`-only lookup could
use, so retirement and the settle sweep scanned whole tables. Additive only; at production's
size both builds are sub-millisecond. The pool also drops from 10+10 to 5+5 — 20 connections
from one container against `max_connections=60` was a third of the instance.
**API-only: `/ship-prod` is owed, and it carries the migration —
`docs/runbooks/migration-026-recovery.md` needs owner sign-off before that upload.**

**Batch 128 made the migration rollback problem a check rather than a habit** (`00d609e`).
Production has no restore point and migrates on boot, so every revision removes the rollback
target until a later shipment applies none — recorded four times as a one-off before anyone
saw it was structural. A batch adding a revision past `025` now fails its own gate without
`docs/runbooks/migration-NNN-recovery.md`, and `/ship-prod` step 1.7 refuses the upload.
`docs/runbooks/migrations.md` is the convention. **Tooling-only; nothing to ship.**

**Batch 145 compressed the Saturday slate** (`f929c3d`). ~84 KB of JSON went down a phone
uncompressed with no `vary: accept-encoding`; measured on a smaller round, 23,205 bytes became
3,131 on the wire. Gzip is added **first so it sits innermost** — above the two
`BaseHTTPMiddleware` layers it never sees a content-length and compresses everything, tokens
included. The 4 KB floor keeps credential-bearing responses (658 bytes) out of it.
**API-only: `/ship-prod` is owed, and production's `content-encoding` is unconfirmed until then.**

**Batch 144 stopped Home reading every round in the deployment twice** (`1bfe512`). The
cross-league summary labelled two sets of rounds and paid the deployment-wide date read for
each, off whole `Gameweek` rows rather than the one column it wanted. `SeasonLabels` resolves
a season once per request; the read is now a distinct projection. 14 statements to 12.
**API-only: `/ship-prod` is owed.**

**A red baseline on `main` with no commit behind it** (`2f7d742`, 23 Sep). The gate was
green at 16:45 UTC and red at 20:39 the same evening: four tests in `test_round_population.py`
named a fixed weekday for a league's slate window, and once the clock passes that weekday's
window time today's cadence date is skipped, leaving the asserted horizon a date short. They
now use the file's own `_future_window`, whose invariant — never today — is itself a test now.
**Test-only; no shipment.**

**Batch 157 dropped the averaged rank from the cross-league summary** (`e8b5fe4`). The
contract says points and win rate aggregate across leagues and rank does not; `me.py`
returned `avg_rank` and `avg_rank_leagues` anyway, ported in with the endpoint. Owner's
decision 2026-09-22 was to drop the pair, not refine the mean — third of fifteen and third
of three are not the same achievement. The per-league ranks in the breakdown are untouched.
Unusually, the web half deploying first is the *safe* order here, so both halves ship in
one commit. **API + web: `/ship-prod` is owed.**

**Batch 119 — discovery could not afford to run, and nothing said so for a week.** Closed out
2026-09-12 (`f69b5fe`). Between 2026-09-04 20:21 and 2026-09-11 **no scheduled job created a
single round**: `fetch_slate` costs one request per competition, `config.py` documented "~30",
and the live catalogue measured **67** — so the daily run was `2 windows x 2 dates x 67 = 268`
requests against a 100/hour plan, took a `429` partway through every morning, and rolled back
everything it had already bought because it committed once at the end. 2-1 Hibs's twelve
members had nothing to play and the 12 September round did not exist until it was created by
hand. Four changes: the owner's product trim (Ireland and `england-amateur-*` except the
National Leagues, measured to remove exactly 13 of the 33 competitions the pool holds), a
daily walk narrowed to the competitions that have ever carried a fixture with a weekly
full-catalogue pass to stop that ratcheting shut, a commit per `(window, date)`, and two
silence alarms on the admin dashboard that cost one query each. Folded in from Batch 115: a
scheduled pass that warms the pricing marker, and dated measurements with a database-backed
tripwire in place of `UK_COMPETITIONS = 30`. Separately, `/odds/multi`'s `400` on one chunk of
ten had been costing the whole card its prices (`fixtures=202 priced=0`, three times in one
evening); a refused chunk is now isolated and the expired id inside it is found and recorded.
**No migration — head stays `023`**, deliberately, so a rollback stays available.

**Batch 116 is complete, merged and live.** Item 1 — a pick alert that names its fixture —
landed on `main` (`b7afab2`) with **migration `024`**. Item 2
resolved to **no code change** (owner decision, 2026-09-12): the screenshot showed every alert
titled with the *league* under an OS line reading "from Coupon", which is the platform's own
attribution for an installed PWA and cannot be suppressed, only renamed — and the owner chose
to leave `short_name` as it is. The row's other candidate, a league whose own name is "The
Coupon", is unreachable today and is now asserted as a known gap rather than closed by guess
(`7967e4d`).

**Batches 112 and 116 shipped on 2026-09-12** (`b95d81dd`, migration `024`), after the
day's 13:30 UTC lock so no round was taking picks during the deploy.
`scripts/check-deploy-drift.sh` reports **in sync**. Batch 112 is live: a league's rounds
are its cadence and nothing else, `POST /leagues/{slug}/gameweeks` now answers `405`, and
`retire_stranded_rounds` deletes a round whose date is not a cadence date for the league's
current window, which holds no picks and has not settled — bounded to today forward, so
history is untouchable. Batch 116's alert now names the fixture it is about.

**Batch 113 is closed on `main`** (`f748117`, migration `025`). One deployment calendar now
stores each season's immutable week-1 Saturday and global extra dates. Public labels derive
from its Wednesday-to-Tuesday football weeks, including `6b`/`6c` suffixes, while
`Gameweek.number` remains the unchanged per-league internal ordinal. The admin Calendar
surface owns anchor and extra-date changes; discovery alone materialises extras, once per
distinct window, and refuses withdrawal after any league has picked.

**Migration `025` and its additive calendar API are live.** The 22 Sep pre-push drift check
reported the deployed API at `2aa02c56` with migration `025`; every later commit on
`origin/main` was documentation and none reached the API image, so nothing is owed. The
production calendar backfill is still separate: run
`python -m src.backfill_season_calendar --dry-run`, review every visible move, and only then
run the separately authorised `--apply`; neither command is part of a normal close-out.

**Batch 117 — home named the round it had finished with, and the coupon was last on the
coupon page.** Closed out 2026-09-12 (`bf87f0a`). `LastResult` had carried `number` since
Batch 79 and `CurrentRound` had nothing, so the live card — the deadline, the member's own
claim, the progress count — was the only thing on home a member could not identify. The API
now sends it and the card names its round exactly when the card is about that round. The
coupon leads the page in every phase instead of only once there was nothing left to do about
it, and its legs fold away so leading with it does not push the slate down by the league's
membership. **A second owner decision was taken rather than deferred:** arriving via the
completion notice, the `#coupon` fragment or `focusCouponSection` opens the section. **The
web half and the `number` field are both live**; the card falls back to the round's date only
for genuinely older data where no number exists.

**Batch 118 — the first impression described a flow that had been deleted.** Closed out
2026-09-12 (`a29662a`), web-only, so it reached members on the push. The invite message told
recipients to "sign in with the display name and PIN from your admin" three weeks after public
signup replaced that; it now leads with a `/join/:token` link when the league has a live one,
keeps the join code as the fallback, and reads correctly for someone opening it on a computer.
`WelcomePage` — per-platform install steps that nothing linked to — is deleted and its content
folded into `BrowserOnboarding`, which is now the single landing surface: a cold browser visit
to `/` is routed to `/welcome`, closing the hole where a desktop visitor met the sign-in form
and no description of the product, and Android now gets manual install steps whether or not
`beforeinstallprompt` fires. **One owner decision was taken rather than deferred and wants
confirming:** the row asks whether desktop is a supported way to play or a prompt to install,
and the majority reading — supported — is what the copy now says.

**Batch 115 is superseded by 119** and stays unchecked rather than struck: its warm pass and
its measurement-not-a-literal principle are both in 119, and the largest-round derivation is
not — 119's verification names the *catalogue*, and re-opening `OBSERVED_LARGEST_ROUND` at 264
would change what the budget certifies, which is a decision rather than a batch.

**Batch 114 — the plan was exhausted on a match morning.** On 2026-09-05 members were refused
with `ODDS_UNAVAILABLE` at 08:06 UTC on a round whose lock was five hours away, because
odds-api.io's 100 requests/hour was already gone. The open round held **202 fixtures, 103 of
them FA Cup qualifying ties**, and Bet365 priced not one of the 103: they cost 11 of every
sweep's 21 requests and rendered as rows no member could ever pick. A fixture now *remembers*
that the bookmaker prices nothing on it (revision 023, re-checked every six hours), those rows
leave the card, a `429` costs one request instead of one per retry, the plan is counted and
shown on the admin dashboard with a floor reserved for the pick path, and the price a member
taps is the price they get — a submission carrying a stale one is refused with `PRICE_MOVED`
and the new number. Measured through the real cache: the tightest browsing hour falls from 42
requests to **20 of 100**, and a saturated day from 564 to **344 of 500**.

**Both things Batch 114 owed are now closed.** It shipped on 2026-09-06 as deployment
`45bca567`, and the temporary override set by hand at 09:02 UTC the previous day —
`ODDS_CACHE_NEAR_TTL_SECONDS` and `ODDS_CACHE_PICK_TTL_SECONDS` both `3600`, deliberately
reversing the *this path must not degrade* rule — was deleted afterwards. That needed a second
deployment (`aadbc897`): `railway variable delete` mints no redeploy, so the serving container
kept reading `3600` from its own env snapshot until it was restarted. Production now reads
`near_ttl 1800` / `pick_ttl 60` with **zero** `ODDS_CACHE_*` keys in the process environment,
so the deployment and `config.py` no longer disagree. The Railway IaC plan was reviewed and
**not applied**: it wanted to delete those same two variables, which `/ship-prod` classifies as
destructive, and doing it that way round would have restarted the *old* image on the defaults
that caused the outage. See the 2026-09-06 shipment entry in
`docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md`.

**Batch 115 is what Batch 114 left open**, specified 2026-09-06 from its own shipment. Two
things, both measured rather than predicted. The marker is written *only* by an authenticated
card load, so fifteen minutes after `023` applied `odds_checked_at_utc` read `never` across all
1,003 fixtures — meaning the first member to open the card on a match morning pays the whole
27-request cold sweep in the hour everyone else is picking, and `refresh_slate`'s docstring
still claims "there is nothing to warm here". And the certification went stale in a day:
Batch 114 recorded a 202-fixture round, production's largest is now **264** with **zero** FA
Cup and an `england-amateur-*` tail instead — the same shape under a different competition
inside twenty-four hours, which is the strongest argument yet for learning per fixture rather
than per competition. Tightening the near tier stays out of scope until the counters have real
data to take the number from.

Batches 112 and 113 were specified on 2026-09-04 and are now closed; 114 was taken before
both on its own instruction, being the live defect. Batch 95 remains in the soft-blocked tail of
Group D. **Groups I through M are complete**, which closes out both the 2026-08-26
full-application review and the owner's 2026-09-03 Coupon, home, notification and Football
Stats review:

```text
I  103 done      web       → no ship owed
J  104 shipped   API+infra → shipped 2026-09-04
K  105 106 done  web       → no ship owed
L  107 108 done  API+web   → shipped 2026-09-04
M  109 110 111   web+API   → shipped 2026-09-04, complete
```

`/group-start <I-M>` now orchestrates those groups. It still gives every batch its own
branch, full gate and automatic close-out; it stops at each API checkpoint for an explicit
`/ship-prod`, then verifies deployment drift before a rerun can continue. There is no batch order left to run: the
wave is finished and only Batch 95's blockers remain.

**Group K is complete.** Batch 105 unified Your pick and Combined coupon into one
state-aware Current round surface and Batch 106 separated future action from historical odds
on home and contained the hero glows. Both are web-only and reached members on their own
close-out pushes; `check-deploy-drift.sh` reports nothing to ship.
Purposeful state colour is folded into those hierarchy changes rather than becoming a
standalone restyle. **Group L is complete.** Batch 107's `X/Y picked` notifications and
durable all-picked transition shipped on 2026-09-04, and Batch 108's final-picker hand-off
and truthful notification copy reached members on its own close-out push afterwards, in that
order and for that reason.

**Group M is one batch in.** Batch 109 turned Football Results from a single column of the
whole archive into a matchday carousel: one result-bearing day on screen, a snapped
swipeable strip of the rest above it, labelled previous/next steps, and the selected day in
the address as `?date=YYYY-MM-DD` — pushed rather than replaced, so the back button walks
out of the archive the way it walked in. Only days that were played are in the strip, an
unresolvable date falls back to the latest day, and competitions stay grouped beneath the
selected date. It is web-only and reached members on its own close-out push, so nothing is
owed. The browser pass at 390×844 caught the one defect the unit tests structurally could
not: `scroll-behavior: smooth` and `scroll-snap-type: mandatory` together refuse a long
programmatic scroll, so on a full season the newest day's chip sat 8,000px off-screen while
its own heading was on display. Batch 110 next persists the full selected league season
including future and non-final fixtures, and Batch 111 then makes league-table teams open
that addressable season view — with a **mandatory `/ship-prod` between them**, because
111's route cannot work against the deployed API.

**Group M is complete.** Batch 111 closed it: a club in a league table is a link now, to
`/football/teams/:teamId?competition=&season=`, showing its whole season — results newest
first, fixtures chronologically, the next playable match marked, and postponed and cancelled
games still visible and named as such. It replaced Batch 53's form-pip disclosure rather than
sitting beside it, because two ways into one thing with one of them invisible was the defect.
The expanded division moved into the URL as part of it, which is what makes the back button
restore both the open table and the member's scroll position. The browser pass caught one
thing the unit tests structurally could not: the club link rendered a 164×20 target, four
pixels under WCAG 2.2 SC 2.5.8 — the same shortfall Batch 55 fixed on the form disclosure.

**Batch 110 shipped on 2026-09-04 and is what Batch 111 reads.** The football store held
finished matches and nothing else — the FotMob adapter discarded every other kind on the
way in — so it could say what a club had done and never what it was playing next. Ingestion
now takes the whole season, which costs no upstream request it was not already paying:
FotMob publishes the season in the payload the league table came from, so the daily job's
date window was only ever deciding how much of what had already arrived got written down. A
provider that pages its results keeps that window. Matches gained a `state` — scheduled,
live, finished, postponed, cancelled — because three `finished = false` rows are three
different things to a reader, and `GET /api/v1/football/teams/{team_id}/season` returns one
club's complete season in one competition, addressed by the club's own id and served from
the database alone. **Migration 022 adds `matches.state`, so the ship carries a migration.**
None of it is live until `/ship-prod`, and Batch 111's team route 404s against the deployed
image until it is.

**Batch 104 was the only item in this plan with an external deadline and is now closed and
live.** `.railway/railway.ts` replaces the deprecated `railway.toml` before Railway's
2026-12-01 cutoff, preserves the one-replica invariant in the image and migration guard,
and is evaluated by both local and GitHub deployment-config gates. The drift watch follows
the new path. Production has served it since the Group J `/ship-prod` on
2026-09-04; that workflow plans and applies the exact fail-closed IaC graph before uploading
source, then verifies the deployed manifest.

`docs/LAUNCH_PLAN.md` has a single open phase, **L5 — Launch and first-Saturday watch**,
with L0-L4 ticked since 2026-08-04.

**Group A (Batches 82, 83, 84, 85) is complete and shipped.** Production serves
`3cb8b4f1` at migration **`017`** after the 2026-08-27 `/ship-prod`, Railway deployment
`caeb17c2-732c-4195-9322-e7b84e7db3d8`. `check-deploy-drift.sh` reports **in sync**.

**Migration 017's unverified precondition resolved clean.** It refuses to run if two
profiles already collide case-insensitively, and whether any did could not be checked
beforehand — the production Postgres host publishes AAAA records only and this workstation
has no IPv6 route, while the project's REST API answers 402 under the egress quota. The
upgrade ran, which is itself the proof no collision existed; confirmed afterwards from
inside the container (`uq_profiles_display_name_lower` present, the old constraint gone,
collision count 0).

**Group B is complete — Batches 86, 88 and 87 are all closed and live, and no
`/ship-prod` is owed.** 86 and 88 were run adjacent because they reshaped the same two
files (`LoginPage.tsx`, `RegisterPage.tsx`), and 88 has now unblocked Group H. Each batch
reached members on its own close-out push, because Vercel releases the web app from `main`
— what the group avoided is the *asymmetry*, since none of it called an API route Railway
was not already serving. That is the difference from the Coupon tab on 2026-08-06.

**Group C is complete and shipped** — Batches 89 and 90 went to production on 2026-08-28.

**Group H is complete.** Batch 102's React Router 7 migration is closed; it is web-only,
so no API shipment is attached to it.

**Group I is complete.** Batch 103 is closed and web-only, so its settings privacy copy and
pending-request confirmations reached members on the close-out push with no API shipment.

**Group J is complete and shipped** — Batch 104 went to production on 2026-09-04 as Railway
deployment `e95ff966`, the first IaC apply of `.railway/railway.ts`, applying **no migration**
(head stays `020`). The record is in `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md`.

**Batch 105 merged the Coupon's two inner screens into one.** `Your pick` and `Combined
coupon` were two tabs over a single weekly job, so the product asked the member which half
they wanted and neither screen could lead with what mattered at the moment they opened it;
each then repeated the other's headings, fold summaries and frozen-price prose to cover the
gap. The shell now has two destinations, **Current round** and **Season**, and Current round
reads the slate and the coupon together and orders itself by a written-down `roundPhase`:
the fixture list leads while a pick can still be made, and the coupon leads once it is worth
having. The honesty case is the point of the phase — a round the deadline caught is labelled
`Incomplete coupon` and names how many members never picked, instead of presenting a
two-fold as a whole coupon to a three-member league.

Its rows were rebuilt around what people actually scan. Person, selection and frozen odds
all wrap rather than truncating; fixture context clamps at two lines and carries only what
the selection does not already say (`Arsenal · v Chelsea`, never `Arsenal · Arsenal v
Chelsea`); the market tag is gone because the selection always expressed it. The same
editing rule shapes the clipboard — one entry per person, and one frozen-odds disclaimer for
the whole coupon rather than the two it used to print. Old links keep working:
`/leagues/:slug/predictions/coupon` redirects into `#coupon` carrying `?gw=` and honouring a
fragment it already had, and `couponSectionPath` is the one helper that mints that address —
**Batch 107's all-picked notification should deep-link with it rather than by hand.**

**Batch 106 gave every home card one explicit state**, and that closed a defect visible on
the commonest Sunday shape in the product: a settled round's pick, fold and combined odds
were printed as the card's body with `Next opens in 2d` beside them, so last week's price
read as the price of the round being counted down to. `homeCardState` names the state first
— **Pick required**, **Pick submitted**, **Round in progress**, **Between rounds** — and the
primary part of the card carries only what that state's next action needs. Everything about
the round just gone moved under `Last result`, which now owns its pick, fold and price;
where the API sends no `last_result`, the panel is built from the settled round itself, so
those figures always have somewhere labelled to live.

While picks are open a card shows that league's own `n of m picked` rather than a fold that
moves on every claim — the fold returns once the round is frozen, which is the one state
where it is a fact about now. Each card answers from its own summary throughout, and the
copy stopped claiming a week that several leagues do not share.

**The hero's corner glows are no longer filtered children.** A `filter` gives a child its
own rendering context and WebKit paints such a child past a rounded parent's corners, which
is why a coloured bloom sat outside the top-right and bottom-left corners in Safari. They
are radial gradients on one clipped layer now — a background, which every engine clips to
`border-radius` — so the fix does not depend on engine-specific clipping. **WebKit could
not be driven on this Mac** (`playwright install webkit` refuses on macOS 13, and Safari
needs `safaridriver --enable`), so the corners were verified in Chromium in both themes at
390×844 and by cropping the screenshots; an owner glance in real Safari is still worth a
minute.

**Batch 107 is closed and shipped** — it went to production on 2026-09-04 as Railway
deployment `1e33a63b`, applying **migration `021`**, and
`scripts/check-deploy-drift.sh` reports **in sync** at `3366b38f`. Pick pushes now read as
one line: `2-1 Hibs` over
`Dave picked Arsenal @ 1.80 · 3/12 picked`. They previously named the league in both the
title and the body of a tray entry that is already league-scoped, and said nothing about the
round; the recovered room went to the one thing a member could not otherwise learn from a
phone — how close the coupon is to being worth copying.

**The denominator counts members, not recipients.** A mute is a statement about a phone
rather than about who still owes a pick, so push subscription and per-league mute decide
delivery and nothing else. Counting recipients would have announced a smaller league than
exists and — the real failure — called a round complete with muted members yet to play.

**The transition to `Y/Y` is its own event and replaces the ordinary alert rather than
following it**: `Dave picked Arsenal @ 1.80 · 12/12 picked — all picks are in`, delivered to
every eligible member *including the final picker*, deep-linked to that exact gameweek's
copy section through the address Batch 105 settled. It is the only pick trigger that tells
somebody what they just did, because they are the one person for whom something changed.

**That event is a row, and it needs to be for two independent reasons.** Two members
claiming the last two selections seconds apart both commit and both then read a full
coupon — so which of them completed the round has no answer in application code, and
`uq_gameweek_completions_gameweek` (migration `021`) decides it: the insert that lands is
the transition. Separately, delivery is blocking webpush calls on a member's request path,
and where a lost pick alert costs nothing this happens once a round — `delivered_at` stays
null until a fan-out finishes, and the next submission on that round claims and retries it.

The successful pick response now carries `picked_count`, `member_count` and `all_picked`,
read once and shared with the push so the screen and the tray cannot disagree. **Batch 108
consumes exactly those fields, which is why Group L had a `/ship-prod` in the middle of it
rather than at the end** — that checkpoint has now been met, so 108 is unblocked.

**Batch 108 closed Group L from the web side.** The member who fills the coupon now gets a
hand-off — **All picks are in — open and copy coupon** — that opens that exact gameweek's
copy section and deliberately writes nothing to the clipboard; the copy control lives where
it lands them and they press it themselves. Who sees it is the part worth knowing: the API
returns `all_picked` to *anyone* submitting into a full coupon, so the client settles the
real question without a new field, on the rule that **a change of pick cannot fill a
coupon**. It moves no count, so "this submission completed the round" is exactly
`all_picked` on a submission by someone who did not already hold a pick.

**The opt-in screen had been promising three notifications the product has never sent** — a
reminder 30 minutes before kickoff, an alert when results landed, and a nudge when the
leaderboard shifted. It now lists the five that exist, including the postponement alert that
hands a member their claim back, and describes the real reminder truthfully: keyed to the
*lock* rather than to kick-off, and only to members who have not picked. In Settings the
per-league switch is **notifications** rather than "reminders" — it gates every league-scoped
push, so a member muting a league to stop being nagged was also switching off the alert that
their pick had been returned.

**API rollback is unavailable until the next non-migrating shipment**, on the standing terms:
a pre-`021` image cannot resolve revision `021` and fails before uvicorn. Recovery is
forward-only and, unusually, cheap — `gameweek_completions` has no dependants, and disabling
Batch 107 needs no migration. Vercel rollback is unaffected.

**Group F is complete and shipped** — Batch 96 went to production on 2026-08-30 as Railway
deployment `7ec86030-9877-434f-beab-f4e942d7c14e`, message `ship production 5634827`,
applying **no migration**. A group of one, deliberately: it changes what every standings
figure means. `check-deploy-drift.sh` reports **in sync**: `/health` serves `56348276` at
`020` and `/health/ready` agrees with `db: ok`.

**Its asymmetry window was nine minutes and benign** — the opposite of Batch 94's. Between
the close-out push at 11:20 and the ship at 11:29 the leaderboard was drawing a
season-bounded screen against an unbounded API, and nothing broke: `/seasons` 404'd, the
season strip hides itself on an empty list, and the standings request carried no `season`
parameter, which the old image ignored. Members saw the screen they saw before.

**Group G is complete.** Batches 98, 97 and 92 are all closed and web-only, so each reached
members on its own close-out push and the group adds no API shipment. The existing
cross-league summary carried every datum the home pass needed; no route was added and the
conditional reorder never fired. The group finished in its normal 98 → 97 → 92 order.

**Group E is complete and shipped** — Batches 91, 93 and 94 went to production on
2026-08-30. The sequencing doc lists the group as 91, 94, 93 but annotates the same line
"94 last"; the annotation won, because its reason is concrete, and the batches ran 91, 93,
94 with the ship following 94 immediately. That kept Batch 94's API/web gap to minutes
rather than leaving a 404 in front of league admins overnight.

**Group D is all but complete — Batches 99, 100 and 101 are closed *and shipped*
(live API `bc8c8191`, migration 019); only Batch 95 remains, and it is soft-blocked.**
Nothing in the group reached members on a close-out push, so the asymmetry pressure Group C
carried was off; the ship it owed has been paid, though no `docs: record the shipment`
commit was written for it. 95 is soft-blocked on establishing Supabase
egress headroom for FEAT-A09 and on an owner choice of off-platform storage destination.

**Batches 99, 100 and 101 are closed.** 95 is the only one left in Group D, and it is soft-blocked — see below.

**Group D applies migrations 018 and 019, so the previous deployment is not a rollback
target.** A pre-`018` image cannot boot against a database stamped `019`. Forward recovery
is cheap for both and is written into each migration: nothing reads `rate_limit_counters`
except the limiter, and an empty table is exactly the state every process had after every
restart before Batch 99, so `alembic downgrade 017` costs at most one window of counts;
019 is an enum value whose downgrade rebuilds the type, mapping any
`football_provider_degraded` row to `backup_failed`, on rows that exist only if the alert
has already fired.

Batch 74 was applied on 2026-08-26, so 2-1 Hibs' rounds read Gameweek 1-4 and the three
renamed members carry their new names.

What is outstanding now:

**The owner and the two renamed members (A and B in the backfill note) have not been told
their sign-in names changed.** Nobody was signed out — the JWT subject is the player id — so
this surfaces only at the next session expiry or PIN reset, which means the failure arrives
days later looking unrelated. `Craig` and both members' old names are also now registrable
by anyone, since a rename releases a name outright where a deletion would have kept it
reserved.

**No `/ship-prod` is owed.** Batch 96 shipped on 2026-08-30 (see Group F above) and
`check-deploy-drift.sh` reports **in sync**. Group E's own ship is paid: it went to
production earlier the same day as Railway deployment
`f28224cd-ef2e-47d1-8112-33c14974fb53`, message `ship production f2d3efd`, carrying Batches
93 and 94 and applying **migration 020**. `check-deploy-drift.sh` reports **in sync**:
`/health` serves `f2d3efd9` at `020` and `/health/ready` agrees with `db: ok`.

**Batch 94's asymmetry window is closed.** Its Activity page 404'd for league admins between
its close-out push and the ship; an unauthenticated probe of
`GET /api/v1/leagues/{slug}/audit-log` now returns `401` where it returned `404`, while an
absent route on the same prefix still returns `404`.

**Batch 93 reached two of three members, and that is the correct result.** The boot task
located all three, delivered to two, and wrote exactly two `display_name_changed` markers.
The third has no active push subscription, so no marker was written and each boot retries —
they have not been told yet. **Watch for that third marker appearing**, not for its absence.

**There is a usable API rollback baseline again — the first since Group C.** Every shipment
from Group C onwards applied a migration, which left each recorded baseline unbootable: a
pre-`N` image cannot locate revision `N` before uvicorn is reached. Batch 96 applied none, so
its baseline **`f28224cd-ef2e-47d1-8112-33c14974fb53`** — serving `f2d3efd9` at head `020` —
runs against the same `020` database the live image does and is a genuine rollback target.
The Vercel baseline is `dpl_FMgyZzio1yiHCcyBnc3tDtyeuZkd` (`14b7785c`). **The next shipment
that migrates removes this again**, so a batch adding a revision should say so loudly.

Everything before it is already live: `check-deploy-drift.sh` at Batch 91 close-out
reported the API serving `bc8c8191` at migration **019** — Batch 101's close-out commit —
so **Batches 99, 100 and 101 are in production**, migrations 018 and 019 applied, and the
commits between were web or docs only.

**That shipment was never recorded in the log, and it cost a session an hour of wrong
conclusions.** Every previous ship left a `docs: record the ... shipment of Batches N-M`
commit; this one did not, so reading the git log alone says the API is three batches
behind, which is false. `/api/v1/health` reports `sha` and `migration` and is the
authority — run `scripts/check-deploy-drift.sh` before asserting a ship is owed, never
`git log` on its own. The earlier shipment record still standing: Batches 82-85 on
2026-08-27 as Railway deployment `caeb17c2-732c-4195-9322-e7b84e7db3d8`, message
`ship production 3cb8b4f`.
**There is no usable API rollback baseline** — `a8ab5234-06c2-41d3-8358-405d95910d15` is
recorded as the previous healthy deployment but a pre-`017` image cannot boot against a
database stamped `017`, so recovery is forward-only until the next shipment that applies no
migration. Vercel rollback is unaffected.

The authenticated SSRF at `POST /push/subscribe` — the review's only HIGH — is closed in
production as of this shipment. It had been open since Batch 63 opened self-registration.

Batches 79-81 went to production on 2026-08-26 as Railway
deployment `a8ab5234-06c2-41d3-8358-405d95910d15`, message `ship production f41a383`,
behind which `134822f6-91f1-4cc1-9d8f-4619a0a84270` (commit `41f4d7df`) is the rollback
baseline — **available**, because this shipment applied no migration, so both images bundle
head `016` and either can boot against the database. `last_result`, `next_opens_at_utc`,
`points_awarded`, `picks_won` and `recent_form` are all live.

Section 4 was **skipped by design**: the Vercel project is GitHub-connected and its
auto-deploy of the same push already held the stable alias as
`dpl_2GudGyA2GvSZWZ3kfju5t56VjF4h`. That was confirmed by fetching all 62 chunks of the
served bundle and finding this shipment's strings in them, not by comparing timestamps —
the alias record has been wrong on timing before.

Post-deploy verification: 18 of 18 public tables carry RLS and the effective
`anon`/`authenticated`/`PUBLIC` table grants are empty; the web root and two deep links
serve one identical SPA asset with the committed security headers; a preflight from the
stable origin returns the exact origin with credentials enabled while a foreign origin is
refused with 400; `/api/docs` 404s; and two bounded log snapshots showed zero errors and
zero matches across six secret-leakage patterns.

**One item was not verified: the 0.25 vCPU / 500 MB service limits.** `railway.toml` does
not declare them and the GraphQL schema reachable from the CLI rejects `cpuLimit` and
`memoryLimit` on `serviceInstances`, so `/ship-prod` step 3 cannot check them the way it
checks replicas, region, sleep, egress and healthcheck — all of which did verify against
the deployment manifest. They are plan defaults and nothing suggests a change; recorded so
the next shipment does not re-derive the same dead end.

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

### Toolchain

- Backend tools: `/Users/craigrobinson/app-starter/apps/api/.venv/bin/`
- Backend import path: `/Users/craigrobinson/the-coupon/apps/api`
- Frontend: Node `20.20.2` and pnpm
- Scratch database: pip `pgserver`

## Batch 1 — Application spine
**Commits:** `8513a02` · verified: Ruff · mypy · 76 pytest · migration + league flow

### Key facts for future sessions
- No local backend venv; use the sibling template venv with this repo's `PYTHONPATH`.
- Scratch database checks use pip `pgserver`.
- The baseline migration contains profiles, tokens, notifications, leagues,
  memberships, join requests, and invites.

**Next:** Batch 2 — Betfair adapter

## Batch 2 — Betfair adapter
**Commits:** `21078d6` · verified: Ruff · mypy · 98 pytest

### Key facts for future sessions
- Domain mapping lives on `BetfairAdapter`; live and canned implementations
  override only raw API primitives.
- `FakeBetfair.with_sample_data()` includes an English top-flight match, a
  Scottish fourth-tier match, a non-15:00 decoy, and one unpriced selection.
- Never use the owner's live account in agent verification.

**Next:** Batch 3 — Pick and scoring engine

## Batch 3 — Pick and scoring engine
**Commits:** `433f0ae` · verified: Ruff · mypy · 116 pytest · scratch migration + pick flow

### Key facts for future sessions
- Gameweeks and fixtures are global; picks are league-scoped.
- The submit endpoint reads odds server-side and snapshots the chosen price.
- HTTP pick-flow tests commit; reset the scratch schema before rerunning them.
- `alembic check` has known model/default drift; `upgrade head` is the gate.

**Next:** Batch 4 — Scheduler

## Batch 4 — Scheduler
**Commits:** `bc40245` · verified: Ruff · mypy · 149 pytest on scratch PostgreSQL

### Key facts for future sessions
- Jobs use Europe/London wall time and own their database transaction.
- The live adapter uses one shared login with keep-alive and transparent
  reauthentication; tests override the dependency with `FakeBetfair`.
- Lock and settlement jobs are also callable from the external cron entrypoint.

**Next:** Batch 5 — Frontend reshape

## Batch 5 — Frontend reshape
**Commits:** `25133f0` · verified: build · TypeScript · 169 Vitest

### Key facts for future sessions
- Pick, combined-coupon, and standings screens use the snake_case API directly.
- Query keys are centralised in `usePickEditor`; standings use
  `['standings', slug]`.
- The top-level coupon is a single-leaderboard MVP; per-league coupon routing is
  later product work.

**Next:** Batch 6 — Verify + rebrand pass

## Batch 6 — Verify + rebrand pass
**Commits:** `72945c0` · verified: 149 pytest + Ruff/mypy · scratch migration · build/TypeScript + 168 Vitest · mocked browser E2E · grep clean

### Key facts for future sessions
- Browser verification uses `tests.e2e_server:app`, disposable PostgreSQL, and
  `FakeBetfair`; production never imports the test control endpoints.
- The MVP default league slug is `the-coupon`; browser storage and cache keys
  use the `coupon_*` namespace.
- Display-name + PIN auth and invite claiming now use only the live snake_case
  API surface.
- Inherited product documentation, assets, routes, scripts, and the temporary
  handoff document were removed.
- The owner's live Betfair account remains outside agent automation.

**Next:** Launch planning (all build batches closed)

## Batch 7 — Odds provider replacement
**Commits:** `c17e996` · verified: 294 pytest + Ruff/mypy · clean scratch migration through `005` · Node build/TypeScript/ESLint + 160 Vitest · production-bundle browser flow · live provider coverage probe

### Key facts for future sessions
- Settlement reads `GET /v3/events/{id}`, never the odds endpoints: once a
  fixture settles `/odds` keeps `status` but drops `scores`, and `/odds/multi`
  omits it entirely. There is no batch form — `/events` ignores an `eventIds`
  filter — so it is one request per unresolved fixture.
- Status is the settlement gate, not the presence of a score. A `pending`
  fixture reports `scores: {0, 0}` and a `live` one reports the score so far;
  the vocabulary is `pending` → `live` → `settled`, plus `cancelled`. Fixtures
  settle from ~2h after kick-off, so the 18:00 Saturday job has ample margin.
- Leagues carry no `country` field — the country is only in the name — and
  England's lower tiers sit under `England Amateur - …`. Matching must strip
  that qualifier and stay exact afterwards, because `Ukraine` begins with `uk`.
- Event `id` is a JSON number and `league` a nested `{name, slug}` object;
  `coerce_numbers_to_str` is what keeps the slate from coming back empty.
- No provider identifier reaches the database. `(fixture, market, outcome)` is
  both the league's uniqueness key and what settlement resolves against, so
  `005` dropped the Betfair market/selection columns rather than renaming them.
- `fetch_odds` runs in the request path against 100/hour and 500/day. The
  launch Saturday's 131 fixtures batch ten at a time into 14 calls, so
  `ODDS_CACHE_TTL_SECONDS` defaults to 900; the daily cap binds first under
  sustained match-day refreshing.
- Errors must never carry the request URL — the API key travels in the query
  string, so `raise_for_status()` would print it into platform logs.

**Next:** Launch L5 — the odds-api.io key must be sealed into production
(`ODDS_API_KEY`) and staging's `BF_FAKE_MODE` migrated to `ODDS_PROVIDER=fake`
before the first-Saturday watch.

## Batch 8 — League-aware coupon
**Commits:** `6d6451e`, `990b6f8` · verified: 286 pytest + Ruff/mypy · Node build/TypeScript/ESLint + 163 Vitest

### Key facts for future sessions
- `DashboardPage`, `CouponPickPage`, and `CouponCombinedPage` have no `:slug`
  route param — they previously hardcoded `DEFAULT_LEAGUE_SLUG` because
  there was nowhere else to read a league from.
- `LeagueContext` now derives `activeSlug`: the last-viewed league from
  `leagueRecency.ts`'s localStorage key if the member still belongs to it,
  else their first league from `/leagues/mine`, else `DEFAULT_LEAGUE_SLUG`
  while that query is still loading/empty.
- `/batch-start` was changed this session to implement and verify a batch
  inline rather than stopping after branch creation; that workflow doc
  change rode along on this branch as its own commit (`6d6451e`).

**Next:** Batch 9 — Coupon presentation

## Batch 9 — Coupon presentation
**Commits:** `3c3f5b5` · verified: 289 pytest + Ruff/mypy · 301 pytest on clean `pgserver` through `007` · Node build/TypeScript/ESLint + 180 Vitest · production-bundle browser flow

### Key facts for future sessions
- `latest_gameweek` takes the maximum `saturday_date`, and two edge-case tests
  in `test_picks_flow.py` commit gameweeks dated *after* `SAMPLE_SATURDAY`. Any
  test that reads the slate endpoint must out-date every other gameweek in the
  shared committed database or it silently asserts against another test's
  gameweek; `_open_sample_gameweek_as_latest` claims a distinct far-future
  Saturday per call. This trap is waiting for Batch 12.
- The browser flow needs `FRONTEND_ORIGIN=http://127.0.0.1:4173`. CORS allows
  exactly one origin and Playwright serves the preview there, so without it
  every login fails silently and the spec only reports "still on /login".
- `odds_format` is display only. `toFractional` snaps to the traditional UK
  ladder rather than converting arithmetically, because the exact fraction of
  1.91 is 91/100 where every real coupon says 10/11.
- `useOptionalAuth` exists so `useOddsFormat` degrades to decimal outside an
  AuthProvider. `CombinedAccaView` and `usePickEditor` are tested without one,
  and how a price is spelled is not worth coupling them to auth.
- The roster discloses nothing new before lock: the slate already labels each
  taken selection with its holder. What it adds is the members who have picked
  *nothing*, who by definition appear nowhere in the slate.
- Fixture-level `taken_by_names` is a list because the selection-level rule
  lets several members hold one game. Batch 10 makes it at most one.

**Next:** Batch 10 — One pick per fixture

## Batch 10 — One pick per fixture
**Commits:** `329daa6` · verified: 289 pytest + Ruff/mypy · 307 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 180 Vitest · production-bundle browser flow

### Key facts for future sessions
- The rule is per-league but uniqueness is a database constraint, and a
  PostgreSQL index predicate cannot join to another table. So `pick_scope` is
  **denormalised onto `picks`** at write time and the fixture key is a partial
  unique index `WHERE pick_scope = 'fixture'`. `picks.pick_scope` is never the
  league's current setting — only the index reads it.
- `uq_picks_league_gameweek_selection` was **kept**, not replaced as the batch
  row said. Fixture uniqueness implies selection uniqueness, so it is true in
  both modes, and it is the only backstop selection-rule leagues have.
- The slate had to change with it: under `fixture`, every selection on a claimed
  game reports that holder, or the coupon offers selections the submit endpoint
  must refuse. Any future read of the slate has to keep honouring the scope.
- Changing a league's scope is a data migration in miniature. Tightening is
  refused with `PICK_SCOPE_CONFLICT` if two members already share a game;
  succeeding restamps **pending** picks only, because a settled gameweek was
  played under the rule then in force.
- Default is `selection` everywhere — column, API, and league creation — so
  nothing changes for an existing league until an admin opts in.
- The pick pool shrinks roughly fivefold under the fixture rule (three
  match-odds outcomes plus two BTTS collapse to one claim). A 15-member league
  needs 15 fixtures, not three. The launch Saturday carries 131.

**Next:** Batch 11 — Daily slate pre-fetch

## Batch 11 — Daily slate pre-fetch
**Commits:** `5b77972` · verified: 314 pytest + Ruff/mypy · 334 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 180 Vitest · production-bundle browser flow

### Key facts for future sessions
- **The daily cap binds, not the hourly one.** 500/day minus ~60 for discovery
  leaves 440 for odds — 31 sweeps of the 131-fixture card at 14 requests each.
  The first tier values written for this batch failed that (704/day) and were
  recomputed backwards from the limit. Any future work that adds request-path
  provider calls must re-run `tests/test_request_budget.py`.
- `fetch_odds(..., max_age_seconds=)` **tightens but never loosens** the TTL.
  Browsing passes the lock-aware tier; the submit path passes 60s for the single
  fixture being picked. That asymmetry — 14 requests to browse the card versus 1
  to freeze a price — is the whole design.
- Consequence for the UI: a browsed price can be up to 30 minutes old near lock,
  so the odds a member taps may differ slightly from the odds they are scored on.
  The submit response carries the actual frozen price.
- Discovery does **not** fetch odds, deliberately. A price only means anything at
  the instant it is frozen, so pre-fetching prices would spend the budget on
  numbers nobody is scored on.
- `refresh_slate` is no longer the midweek job — it is the Saturday late pass.
  `discover_fixtures` covers midweek. Both are idempotent on `(gameweek,
  provider_event_id)`.
- Three places must stay in step when a job is added: `create_scheduler`,
  `run_scheduled.JOBS`, and their two guard tests in `test_scheduler.py` /
  `test_run_scheduled.py`, which assert the exact job set and cron strings.

**Next:** Batch 12 — Gameweek history

## Batch 12 — Gameweek history
**Commits:** `1be9f0d` · verified: 314 pytest + Ruff/mypy · 337 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 182 Vitest · production-bundle browser flow

### Key facts for future sessions
- `resolve_gameweek(db, gameweek_id)` is the single entry point for "which
  gameweek is this read about". The slate and coupon both go through it, so
  anything added later that reads a gameweek should too, or the two surfaces
  will disagree about what "current" means.
- React Query keys are `['gameweek', slug, gameweekId]` and
  `['coupon', slug, gameweekId]`, with `undefined` meaning latest. Invalidation
  after a grab is **prefix-matched** on `['gameweek', slug]` so every viewed
  week refreshes, plus `['gameweeks', slug]` for the season list's pick counts.
- Selection lives in the `?gw=` search param, not component state. That is what
  makes a past week linkable and back-button-navigable, and it means the default
  URL stays clean and the default query key stays stable.
- A `gameweek_id` that is not a UUID is a **404, not a 500** — the value comes
  straight off the query string, and an impossible id is a miss like any other.
- `test_picks_flow.py`'s `_open_sample_gameweek_as_latest` (added Batch 9) is
  what makes these tests possible: each call claims a distinct far-future
  Saturday, so a test can create two gameweeks and know which one is newest.
- The season list is unpaged on purpose — about forty rows a season.

**Next:** Batch 13 — Profile

## Batch 13 — Profile
**Commits:** `096818f` · verified: 314 pytest + Ruff/mypy · 340 pytest on clean `pgserver` through `008` · Node build/TypeScript/ESLint + 186 Vitest · production-bundle browser flow

### Key facts for future sessions
- The profile is **per-league**, and that was the open decision in the batch row.
  Picks are league-scoped, and since Batch 10 the claim rule is too, so a career
  total would sum leagues playing different games. Route is
  `/leagues/:slug/players/:playerId`.
- Season figures come from `standings()` rather than a second query, so the
  profile and the leaderboard cannot drift apart. Anything added to one should
  be added there, not recomputed.
- `win_rate_pct` is `null`, not `0`, before anything settles — an untested
  record is not a bad one. The page renders "—" and says why.
- History excludes `pending` picks on purpose: an unsettled pick is already on
  the coupon, and repeating it here would be a worse copy of that view.
- Only ~130 of the source page's 774 lines were applicable. The World Cup
  predictor's exact-score rate, streaks, submit timing, and group/knockout
  sections have no counterpart in an accumulator game. Avatar **upload** was not
  ported — Launch L1 removed it deliberately.
- Reading a profile requires membership of the league it is read through
  (`LeagueMemberDep`), and a player not in that league is a 404, not an empty
  record.

**Next:** Batch 14 — Per-league gameweeks (the architectural pair with Batch 15)

## Toolchain trap found closing Batch 13
**Commit:** `48a7a58`

CI pins `ruff==0.5.4` (`apps/api/requirements-dev.txt`, `pyproject.toml`) but the
local toolchain `/batch-verify` mandates — app-starter's venv — ships **0.16.0**.
They format `assert X, (msg)` differently, so a locally-clean file can fail CI.

It went unnoticed for three batches because `ruff format --check` is the **first**
backend step: it failed the job before `mypy`, `alembic upgrade head`, and
`pytest` ever ran, so Batches 11-13 merged onto a red main and the DB-backed
suite was never actually exercised remotely. It has been since — 340 passed in CI
on `48a7a58`, migration `008` applied.

Check formatting with the pinned version, not the venv:

    cd apps/api && uvx ruff@0.5.4 format --check . && uvx ruff@0.5.4 check .

A green local gate is not evidence of a green CI until this is reconciled.

## Batch 14 — Per-league gameweeks
**Commits:** `3d95e5e` · verified: 331 pytest + Ruff/mypy · 365 pytest on clean `pgserver` through `009` · pre-009 backfill + downgrade round-trip · Node build/TypeScript/ESLint + 186 Vitest · production-bundle browser flow

### Key facts for future sessions
- **`saturday_date` is now `starts_on`, and it is not necessarily a Saturday.**
  `gameweeks` is unique on `(league_id, starts_on)`; `fixtures` is a pool unique
  on `provider_event_id`; `gameweek_fixtures` says which pooled fixtures a round
  plays. A fixture no longer names its round.
- `SlateWindow` (in `odds_provider.py`, so the port stays ORM-free) replaced
  `SATURDAY`/`KICKOFF_HOUR`/`_LOCK_HOUR`/`_LOCK_MINUTE`/`_SATURDAY`. It is a
  **range**, and today's rule is the degenerate case where start equals end.
  `query_bounds` is deliberately wider than `contains` — providers filter by
  range, so a point window still has to be asked for as a whole day.
- **Discovery groups by window, not by league.** That is the only reason
  per-league windows do not multiply the provider bill. Anything that adds a
  provider call per league will break the 500/day budget; there is a test.
- `POST /picks` resolves the round from **league + fixture**, preferring a
  still-open one. If Batch 15 lets windows overlap more, an explicit
  `gameweek_id` on submit may become the better API.
- A clean-DB `alembic upgrade head` proves nothing about a data migration.
  `tests/test_migration_009.py` builds its **own** database, migrates to `008`,
  writes pre-split shapes, then upgrades — and that is what caught 009 dropping
  the old global unique key *after* the clones that violate it.
- The scheduler crons no longer filter on a weekday. A Saturday-only
  `lock_gameweeks` would never lock a Friday league's round.
- Deleted `_open_sample_gameweek_as_latest` (Batch 9) — it only existed because
  `saturday_date` was globally unique.

**Next:** Batch 15 — League admin configuration (builds directly on this migration)

## Batch 15 — League admin configuration
**Commits:** `4cb6267` · verified: 331 pytest + Ruff/mypy · 378 pytest on clean `pgserver` through `010` · 010 up/down round-trip + defaults + non-empty check · Node build/TypeScript/ESLint + 192 Vitest · browser e2e is owner-run (`ODDS_PROVIDER=fake`)

### Key facts for future sessions
- **Competition selection is a link-time filter in `sync_slate`, never a provider-query
  change.** `leagues.competitions` is JSONB: `NULL` = all UK, a `[{slug,name}]` list narrows
  which pooled fixtures a round links. The per-window fetch is still all-UK, so the request
  budget and the "discovery groups by window" tests are untouched. `sync_slate` now returns
  `Gameweek | None` (no empty round for an excluded window) and still never unlinks.
- **`offered_markets` is `pick_market[]` — an array of the *existing* enum, not new values.**
  Widening the markets themselves is still a migration. Enforced twice: the slate read
  (`_selection_options`) hides them, and submit rejects with `MARKET_NOT_OFFERED`.
- **`PickMarket` now lives in `models/league.py`** (re-exported from `pick.py`, so
  `from src.models.pick import PickMarket` still works). It moved to let `League.offered_markets`
  type against it without a league↔pick import cycle.
- **The competition catalogue (`GET /{slug}/competitions`) is `SELECT DISTINCT competition_id,
  competition FROM fixtures`** — zero provider cost, but empty until discovery has pooled
  fixtures (production had none at close-out; the default all-UK works without it).
- **Ad-hoc round `POST /{slug}/gameweeks` walks the provider in the request path** (~one
  `/events` per UK competition), so it is rate-limited to 6/hour. A past date gives an
  already-locked (unpickable) round; a date with no qualifying fixtures is `422 NO_FIXTURES`.
- **`competitions` on PATCH uses `model_fields_set`** to separate "omitted (unchanged)" from
  "explicit `null` (all UK)"; every other field keeps the null-means-unchanged convention.

**Next:** Batch 16 — Football data (real tables/results/form; needs a second provider). Launch
L5 — launch and first-Saturday watch runs in parallel.

## Batch 16 — Football data
**Commits:** `10f11f4` · verified: 375 pytest + Ruff 0.5.4 check/format + strict mypy · 453 pytest on clean `pgserver` through `011` · Node build/TypeScript/ESLint (0 errors) + 217 Vitest · browser flow driven locally against `tests/e2e_server` (`ODDS_PROVIDER=fake`, canned football), mobile + desktop, light + dark

### Key facts for future sessions
- **The 100-requests-a-*day* free plan is the whole design, not a caveat.** Nothing may
  reach a football provider from the request path — ingestion writes `teams`/`matches`/
  `standings` on the 06:30 job and every screen reads those. `tests/test_football_router.py`
  booby-traps `football_session.acquire` and asserts both endpoints still answer, so a
  future provider call in a read path fails loudly.
- **A competition costs exactly two requests** (`/standings` + `/fixtures`), so 30 UK
  competitions is 61 with the memoised catalogue. `FOOTBALL_COMPETITIONS_PER_RUN` caps a
  run and `pooled_competitions` orders least-recently-synced first; the season backfill is
  a deliberate one-off (`python -m src.run_scheduled football-backfill`), never scheduled.
- **`standings.updated_at` is stamped by hand in `sync_table`.** `UpdatedAtMixin` has no
  `onupdate` and there is no trigger, so it froze at insert — which broke the "as of" line
  *and* froze the rotation ordering, starving every competition past the cap after the
  first pass. A server default is no use either: `NOW()` is the transaction's start time,
  so one run's competitions would share an indistinguishable timestamp.
- **Aliases are learned at ingestion, not read time**, which is what makes the pick screen's
  inline form a primary-key lookup. `resolve_names` refuses ambiguous names outright — two
  clubs equally close resolve to nothing, because no form line beats the wrong club's.
- **`FOOTBALL_DATA_PROVIDER` defaults to `none`** so sealed production is untouched; `none`
  disables *ingestion* only and the screens still read what is stored. The canned data is
  season 2025 while the canned slate is 2026-27, so anything using `FakeFootballData` must
  pin `FOOTBALL_SEASON=2025` (`tests/e2e_server.py` sets it directly).
- **`apps/web/.env.local` on this machine points at a dead wc2026 Railway URL**, so the web
  dev server never reaches a local API until it is repointed. It is gitignored, so this is a
  machine artifact rather than a repo bug — but it silently renders every screen empty.

**Next:** Batch 17 — Betslip export spike (timeboxed, ends in an ADR). Launch L5 — launch and
first-Saturday watch runs in parallel.

## Batch 17 — Betslip export spike
**Commits:** `12ffcb4` · verified: 375 pytest + Ruff 0.5.4 check/format + strict mypy · Node build/TypeScript/ESLint (0 errors) + 217 Vitest · no DB or browser gate — the batch ships no code, so neither is in scope

### Key facts for future sessions
- **The decision is not to build betslip export**, and the ADR is the whole batch —
  `docs/adr/0004-betslip-export.md`. Two walls, either sufficient alone: nothing we can
  generate composes an accumulator, and `odds_at_pick` is frozen, so any exported acca
  prices live at the book and disagrees with the coupon's headline number every week.
- **Bet Share and the affiliate link split the two capabilities and never combine them.**
  Bet Share carries a full acca but is minted inside an authenticated Bet365 session, from
  a bet the customer already holds — only they can create it. The affiliate
  add-to-betslip link is one we *could* create, with a Bet365 Partners account, and carries
  exactly one selection. Booking codes elsewhere (Betway Book-a-Bet, Betano) are the same
  shape: customer-minted, multi-leg. That is why the only low-friction design is a captain
  relaying their own link, not us generating one.
- **odds-api.io already returns bookmaker links and we discard them.** `/odds` carries an
  event-level `urls` map (`{"Bet365": ...}`) plus `homeLink`/`drawLink`/`awayLink` per
  entry. `OAEventOdds` doesn't declare `urls` so pydantic drops it, and `_selections_for`
  (`services/odds_api.py:494`) reads only the price keys, so the links sit unread in dicts
  we already hold. Surfacing one costs zero extra requests — cost was never the obstacle.
  There is no `yesLink`/`noLink`, so BTTS is unlinkable regardless.
- **Logging into a member's Bet365 from the app was considered and rejected.** PINs are
  bcrypt-hashed and unrecoverable; replaying a bookmaker login needs a *reversible* secret,
  which this app has never held, guarded by a 4-digit PIN. Bet365's terms also prohibit
  automated access, and the realistic outcome is a member's account suspended with funds
  frozen. Not in the ADR — worth adding if it is asked again.
- **An outbound bet link changes the product's regulatory category.** There is no age gate,
  no date of birth, and no responsible-gambling copy anywhere in `apps/web/src` or
  `apps/api/src`, which is fine for a points game and not fine for a surface that routes
  people to a bookmaker. Age-gating is the precondition for any bookmaker link, not a
  follow-up to it.
- **The odds-api.io Zscaler block is gone** (rechecked 2026-08-06: `api`, `api2` and `docs`
  all answer from their real origins). Live probes are still owner-run, but because no
  `ODDS_API_KEY` exists on this machine — a credentials problem a key would fix, not a
  network one needing a different connection.

**Next:** the build plan is complete — Batches 1–17 all struck. Launch L5 — launch and
first-Saturday watch is the only open phase, and production is still not playable: it runs
the pre-Batch-7 build with no `ODDS_API_KEY` sealed.

## Batch 18 — Production static assets
**Commits:** `e28155c` · verified: lint · typecheck · build (precache manifest checked) · 217 Vitest

### Key facts for future sessions
- `vercel.json`'s SPA-fallback rewrite excluded `icons/`, a directory that never existed;
  the eleven root-level static files (`fonts/*.woff2`, five `icon-*.png` in the manifest,
  `apple-touch-icon.png`, `coupon-icon.svg`) all fell through to `index.html` in
  production and were precached as HTML by the service worker, breaking fonts and the
  installed-app icon.
- Fix is `fonts/|icon-|apple-touch-icon\.png|coupon-icon\.svg` added to the negative
  lookahead — verified with a regex simulation against all eleven paths plus the existing
  SPA and static-passthrough cases, not by deploying.

**Next:** Batch 19 — Coupon page crash.

## Batch 19 — Coupon page crash
**Commits:** `6c71163` · verified: lint · typecheck · build · 234 Vitest

### Key facts for future sessions
- The "Something went wrong" report was a stale route chunk, not coupon code: every route
  is `lazy()`, a deploy drops the previous build's chunk hashes, and `sw.ts`'s
  `skipWaiting()`/`clientsClaim()` hands an open tab to the new worker while it still runs
  old JS — so the *first* route change after a deploy 404s.
- Reproduced against a real production bundle (`vite build` → `vite preview`) by deleting
  a built chunk after load and navigating to it — see `docs/adr/0005-stale-chunk-recovery.md`.
- Fix is `lib/lazyRoute.ts`: wraps `React.lazy`, matches the rejected-import wording across
  Chrome/Firefox/Safari/Vite, reloads once (skipped offline or within a 30s cooldown), and
  lets `ErrorBoundary` show a "Coupon has been updated" message with only Reload — not "Try
  again", since React caches a rejected `lazy` payload permanently.
- Applies to all eighteen routes and `Layout`, not just the coupon pages — the coupon was
  simply the first tap after a deploy, not a special case.

**Next:** Batch 20 — League identity, profile and invite wayfinding.

## Batch 20 — League identity, profile and invite wayfinding
**Commits:** `a784ca6` · verified: Ruff 0.5.4 check/format · strict mypy · 375 pytest · lint · typecheck · build · 234 Vitest

### Key facts for future sessions
- Three built-but-unreachable surfaces, no API change: `DashboardPage` never named the
  active league (fixed via the `PageHeader` eyebrow, which covers all three home cards, not
  just one); there was no self-profile route (added "My profile" to both `TopBar`'s avatar
  menu and `TabBar`'s mobile More sheet, pointing at `/leagues/${activeSlug}/players/${player.id}`);
  and `LeagueJoinRequestsPage`/`LeagueAdminInvitesPage` were routed but linked from nowhere
  (added admin-only buttons to `LeagueActionsMenu`, behind its existing `isAdmin` guard).
- `SettingsPage` already linked to `/about`, which had no route — the catch-all silently
  bounced it home. Added `AboutPage.tsx` reusing the existing scoring-rules copy from
  `OddsGuide.tsx` rather than writing new copy.
- `TopBar`/`TabBar` now call `useLeague()`, so any test rendering them needs a
  `LeagueProvider` (or a `@/contexts/LeagueContext` mock) in the tree — updated
  `TopBar.test.tsx`, `TabBar.test.tsx`, and `accessibility.test.tsx` accordingly.

**Next:** Batch 21 — Competition catalogue from the provider.

## Batch 21 — Competition catalogue from the provider
**Commits:** `74378f8` · verified: Ruff 0.5.4 check/format · strict mypy · 382 pytest (461 on clean `pgserver` through `011`) · lint · typecheck · build · 235 Vitest · browser picker against `tests/e2e_server`

### Key facts for future sessions
- `fetch_competitions()` is an `@abstractmethod` on `OddsProvider`, chosen over a
  non-abstract default returning `[]`: a default would have left `FakeBetfair` — which
  backs every test, staging, and the browser flow — showing exactly the empty picker the
  batch existed to fix. The cost is four implementations, all a few lines.
- **Do not name a port method `list_competitions`** — `BetfairAdapter` already has one as
  a raw primitive with a different signature, so the port method is `fetch_competitions`.
- `OddsApiProvider._uk_leagues()` is now shared by `fetch_slate` and `fetch_competitions`,
  so the picker cannot offer a competition the slate ignores or hide one it takes.
  `_all_leagues()`'s per-client memo is what keeps the endpoint free of an upstream
  request; `CachingOddsProvider` therefore delegates it *uncached* on purpose.
- The endpoint keeps the old `SELECT DISTINCT … FROM fixtures` query as an
  `OddsProviderError` fallback. The picker is also how an admin *un*-narrows a league, so
  a 503 would leave them unable to change a selection they can no longer see.
- `fixtures` is a pool shared by every league, so "this league has pooled nothing" is not
  assertable in the committed test database. The discriminator is the canned
  `Spanish La Liga` (`99999`): `fetch_slate` drops it on the country rule, so no round can
  ever pool it and its presence proves the catalogue came from the provider.
- **`apps/web/.env.local` points the dev server at the production Railway API.** Any local
  browser check must override it (a `.env.development.local` wins and is gitignored) or it
  silently drives production.

**Next:** no build batches remain open; Launch L5 — launch and first-Saturday watch.

## Batch 28 — Football ingestion rate limiting
**Commits:** `d77062a` · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- API-Football's free plan has two limits, not one: 100/day and 10/minute. ADR 0003 now
  records both because missing the minute cap is what made production ingestion write
  nothing.
- The minute throttle arrives as HTTP 200 with `errors.rateLimit`, so the adapter now
  treats that body key as transient and retries through the existing backoff path.
- Scheduled `sync_football_data` spaces competition attempts by
  `FOOTBALL_COMPETITION_SPACING_SECONDS` (default 12.0), sleeping only between attempts
  and injectable in tests.
- A 30-competition sweep is now expected to take about six minutes, which is fine for the
  06:30 scheduler job and is why this belongs off the request path.

**Next:** Batch 22 — Wayfinding and layout.

## Batch 22 — Wayfinding and layout
**Commits:** `ee888f7` · verified: Ruff 0.5.4 check/format · strict mypy · 387 pytest · lint · typecheck · build · 240 Vitest

### Key facts for future sessions
- Football is now top-level wayfinding on both desktop `TopBar` and mobile `TabBar`,
  while `CouponSubNav` still keeps it beside the pick and combined-coupon surfaces.
- The Coupon nav item excludes `/predictions/football`, and both navs set current state
  explicitly so Football does not double-highlight Coupon for sighted users or screen readers.
- `PageHeader`'s action wrapper changed from `shrink-0` to a shrinkable max-width wrapper;
  `LeagueActionsMenu` keeps its own `flex-wrap`, so future phone overflow fixes should avoid
  reintroducing a non-shrinking parent.
- Members administration is now behind the existing `isAdmin` prop; regular members should
  use the leaderboard as the member list.
- Combined coupon rows and profile history rows now render the `competition` field that the
  API already supplied on `CouponLeg` and `SettledPick`.
- The close-out gate exposed an ASCII-locale health bug: `apps/api/alembic.ini` had a
  non-ASCII comment, so Alembic config parsing failed and `/health` reported
  `migration: unknown`; the file is ASCII now and reports `011`.

**Next:** Batch 23 — Slate ordering and collapse.

## Batch 23 — Slate ordering and collapse
**Commits:** `f5496e1` · verified: Ruff 0.5.4 check/format · strict mypy · 387 pytest · clean pgserver migration + DB slate test · lint · typecheck · build · 241 Vitest · production-preview Playwright coupon flow

### Key facts for future sessions
- `FixtureSlate` now exposes `competition_id`; the picker groups and sorts on that stable provider slug, not sponsor-prone display names.
- Competition groups are closed by default so a large slate scans as league headers first.
- The picker order is England top four, Scotland top four, remaining England/Scotland tiers, then everything else by fixture count.
- `GameweekMember` now carries `competition`, and the roster renders it beside the picked market.
- The browser flow opens competition sections explicitly and stores Batch 23 screenshots in `artifacts/batch-23/`.

**Next:** Batch 24 — Share the coupon as text.

## Batch 24 — Share the coupon as text
**Commits:** `b3139d3` · verified: lint · typecheck · build · 243 Vitest (incl. new clipboard/copy coverage)

### Key facts for future sessions
- `CombinedAccaView.tsx` exports `buildCouponShareText(coupon)`, a pure function rendering legs,
  selections, prices and combined odds as plain text with a note that prices were frozen at pick
  time — no bookmaker link, satisfying ADR 0004's second wall.
- The "Copy text" button uses `navigator.clipboard.writeText` and toasts success/failure; no new
  API surface, since `GET /leagues/{slug}/coupon` already carries every field used.
- Frontend-only batch; backend, migrations and Ruff/mypy/pytest gates were untouched and not rerun.

**Next:** Batch 25 — Gameweek results.

## Batch 25 — Gameweek results
**Commits:** `51d0258` · verified: Ruff 0.5.4 check/format · strict mypy · clean pgserver migration + 388 pytest (incl. new DB-backed results test) · lint · typecheck · build · Vitest (incl. new ResultsPage suite)

### Key facts for future sessions
- New `GET /leagues/{slug}/results` (`src/routers/coupon.py`) backed by `scoring.gameweek_results()`:
  one query over every settled round, winner(s) by top `points_awarded` (ties named together),
  `all_won`/`combined_odds` computed the same way `coupon.build_coupon` does.
- A settled round with zero picks in a league still gets a row (`winner_names: []`,
  `all_won: null`) rather than being silently dropped — the outer-join keeps it visible.
- Frontend: new `/predictions/results` (`ResultsPage.tsx`) added to `CouponSubNav`; each row
  navigates to `/predictions/coupon?gw=<id>`, which `useGameweekHistory`'s `gw` query param
  already resolves to that round.
- `PlayerProfilePage` now links to Results ("How each week went") — profile still answers
  per-pick, results answers per-week; neither replaces the other.
- No browser/Playwright check this batch — a local `pnpm dev` server points at the production
  Railway API by default (`apps/web/.env.local`), so verification relied on the DB-backed
  pytest test and the Vitest suite instead of a live preview.

**Next:** Batch 26 — Multi-league home and profile.

## Batch 26 — Multi-league home and profile
**Commits:** `780f70e` · verified: full `scripts/ci-local.sh` PASS (11 checks) — Ruff 0.5.4 check/format · strict mypy · clean pgserver migration + 473 pytest (incl. 5 new DB-backed cross-league tests) · lint · typecheck · build · Vitest 265 (incl. new DashboardPage + CareerProfilePage suites) · prod-bundle Playwright smoke · extended production-preview coupon-flow e2e with screenshots in `artifacts/batch-26/`

### Key facts for future sessions
- New `GET /api/v1/me/cross-league-summary` (`src/routers/me.py`): five fixed queries whatever the
  league count. `per_league` carries slug/name/rank/member_count/points **and** `current_round`
  (status, `locks_at_utc`, `leg_count`, `combined_odds`, `my_pick`), so home is one request rather
  than three per league.
- `scoring.standings_by_league(db, league_ids)` is the new primitive — one grouped query for a set
  of leagues — and `standings(db, league_id)` is now a one-id wrapper over it. Any future
  multi-league read should use it rather than looping `standings`.
- Aggregation rule, encoded in the response: points/win rate sum across leagues (same
  `round(odds × 10)` scale); rank does not. `_MIN_MEMBERS_FOR_AVG = 3` excludes leagues too small
  to rank against from `avg_rank`, and `avg_rank_leagues` reports how many it actually spanned.
- `LeagueContext` gained `selectLeague(slug)`. `activeSlug` is *derived*, so writing the recency
  store alone does not re-render — a screen that opens a league other than the bound one must call
  this, not `setLastViewedLeague`.
- My profile is now `/profile` (career-scoped) in **both** `TabBar` and `TopBar`'s avatar menu;
  `/leagues/:slug/players/:playerId` is unchanged and still reached from that league's leaderboard
  and from the career breakdown.
- Browser verification is viable again despite `.env.local` pointing at production: build with
  `VITE_API_URL=http://127.0.0.1:8000` against `uvicorn tests.e2e_server:app` on a scratch
  pgserver, then run `playwright.config.ts` (the `coupon-flow` project seeds/locks/settles itself).

**Next:** Batch 27 — Configurable pick-open time.

## Batch 27 — Configurable pick-open time
**Commits:** `007ec97` · verified: full `scripts/ci-local.sh` PASS (11 checks) — Ruff 0.5.4 check/format · strict mypy · clean pgserver `alembic upgrade head` (001→012) + pytest · deployment-config assertions · lint · typecheck · build · Vitest 273 · prod-bundle Playwright smoke. Separately: the DB-backed Batch 27 set on its own clean pgserver, 63 passed / 0 skipped.

### Key facts for future sessions
- Three instants now, and the names matter: `SlateWindow.opens_at` is when the *fixture window*
  opens (the anchor), `locks_at_utc` is when claiming stops, `picks_open_at_utc` is when it
  starts. Both offsets are measured back from the anchor via `SlateWindow.utc_before_open`, so a
  **bigger** offset is **earlier** and `pick_open_offset_minutes >= lock_offset_minutes` is the
  validity rule (enforced in the API as 422 *and* by a DB check).
- `pick_refusal(gameweek, now)` in `services/gameweek.py` is the single gate — `is_open_for_picks`
  is now a thin wrapper. Time decides both ends; `status` only rules out rounds settlement has
  finished with. So a `scheduled` round past its instant is accepted *before* the hourly open job
  relabels it, exactly as an `open` round past its lock is refused before the lock job runs. Any
  new caller should use `pick_refusal`, not read `status == open`.
- `pick_open_offset_minutes` lives on `League`, deliberately **not** on `SlateWindow`:
  `discover_fixtures` groups leagues by window, so putting it there would multiply the provider
  bill by the number of distinct announcements. `test_the_pick_open_offset_is_not_part_of_the_window_identity`
  pins this — do not "tidy" it into the dataclass.
- `NULL` on both new columns is the pre-batch rule (claimable from discovery), so 012 needs no
  backfill. On PATCH, `pick_open_offset_minutes` is read from `model_fields_set` because null is
  meaningful ("stop announcing"), the same treatment `competitions` already gets.
- **jsdom form-submit trap, cost ~2h this batch.** `LeagueSettingsPage`'s name input is `required`
  and is filled by an effect *after* the query resolves. A test that waits only for a rendered
  element can click Save while it is still empty, and jsdom then refuses to dispatch `submit` at
  all — no handler, no toast, no PATCH, and a `waitFor` that can only time out (raising the
  timeout does not help). Await `findByDisplayValue('The Coupon')` before clicking Save. The
  Batch 15 test `widens the window and saves the new range` still has this latent.
- `slate_odds_max_age` gives every non-`open` state the loosest tier, so a `scheduled` round whose
  opening has passed shows browse prices up to `far_ttl` until the hourly job flips it. Display
  only and bounded by an hour — submits price independently via `odds_cache_pick_ttl_seconds`.

**Next:** all 28 build batches are struck. Launch phase L5 — Launch and first-Saturday watch.

## Batch 33 — Football ingestion shape tolerance
**Commits:** `df53b49` (scope) · `94715a9` (fix) · verified: full `scripts/ci-local.sh` PASS (11 checks) — Ruff 0.5.4 check/format · strict mypy · clean pgserver `alembic upgrade head` + pytest (incl. 4 new adapter tests) · deployment-config · lint · typecheck · build · Vitest 273 · prod-bundle Playwright smoke

### Key facts for future sessions
- **A pydantic default covers an *absent* key, not one present as `null`.** API-Football sends
  `"code": null` for the countryless competitions and `"form": null` until a team has played, and
  `str = ""` rejects both. `AFModel`'s before-validator drops nulls so null reads as absent for
  every raw payload model — patch new fields there, not one field at a time.
- The catalogue is the one parse **every** competition shares, so it is the only one that needs
  per-entry tolerance; `_all_leagues` now drops an unreadable row and memoises the survivors.
  Per-competition parses need none — `sync_football_data` already isolates a failure to its own
  competition.
- Raising before a memo is assigned is a quota bug, not just a correctness bug: it cost a fresh
  `/leagues` request per competition, 21 of 100 in one morning. Any future memo on this client
  must be assigned even on partial success.
- **Coverage is still unobserved.** Only the catalogue request has ever succeeded against the live
  API. The next run answers it: `api-football catalogue loaded leagues=N dropped=M`, then one
  `api-football competition unmatched` per division that fails to resolve. Read those before
  treating the Football tab as fixed.
- Ingestion cost ceiling, recorded not fixed: 1 catalogue + 2 requests per competition against
  100/day caps a day at ~49 distinct competitions, and `FOOTBALL_COMPETITIONS_PER_RUN` defaults to
  30. Past that the rotation still feeds everything but no table is fresher than ⌈union ÷ cap⌉
  days — the symptom of many leagues is **stale** tables, not missing ones.
- `LeagueSettingsPage.test.tsx`'s `loads a stored offset with the switch already on` is **flaky**
  and failed this batch's first gate run before passing twice: `findByRole` waits for the switch
  to exist, but it renders `aria-checked="false"` and only flips once the query resolves. Batch
  27's log predicted this class in this file. Wait on the settled value, not on presence.

**Next:** Batches 29-32 are open (start with 29 — League identity on the coupon tab). Batch 33 needs a `/ship-prod`; the Football tab stays dark until the API moves and `sync-football` runs.

## Batch 29 — League identity on the coupon tab
**Commits:** `57c8cb3` · verified: frontend gate — `pnpm lint` (0 errors, pre-existing warnings only) · `pnpm typecheck` clean · `pnpm build` succeeds · `pnpm test` 38 files / 285 tests pass (12 new/updated, covering league-name headers, the switch strip on multi-league members, and the no-league gate). Frontend-only batch; backend/DB checks out of scope.

### Key facts for future sessions
- `LeagueContext` now exposes `activeLeagueName` and `hasLeagues` alongside `activeSlug` —
  `hasLeagues` is `leagues.length > 0` and is the correct gate for any query that binds to
  `activeSlug`, since that falls back to `DEFAULT_LEAGUE_SLUG` while `leagues` is loading/empty.
- `LeagueSwitchStrip` now calls `selectLeague(currentSlug)` in its mount/update effect instead of
  writing the recency store directly. This closes the drift Batch 29 was scoped from: browsing
  `LeaderboardPage` (URL-driven slug) previously updated the store but not `activeSlug`, so a later
  tap on the Coupon tab (`activeSlug`-driven) could silently reopen the wrong league.
  `selectLeague` still writes the store itself, so no caller needs both.
- `useGameweekHistory(slug, enabled = true)` gained an `enabled` param so `CouponPickPage` and
  `CouponCombinedPage` can defer the `/gameweeks` fetch until `hasLeagues` is true, matching the
  gate now applied to every other coupon-surface query.
- The four `/predictions/*` pages share one "You're not in a league yet" empty state (title +
  "Find a league" link), copied from `DashboardPage`'s pattern rather than factored into a shared
  component — kept inline per-page since each needs a different early-return shape around its own
  header.
- Slug-addressed coupon routes (making the binding shareable/bookmarkable) are explicitly out of
  scope here — that is Batch 30, next.

**Next:** Batch 30 — Slug-addressed coupon routes.

## Batch 30 — Slug-addressed coupon routes
**Commits:** `f33674d` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build (39 files / 306 tests), Playwright prod-bundle deep-link smoke. Plus the full browser end-to-end (`coupon-flow`, production preview + scratch PostgreSQL + `FakeBetfair`) — 1 passed, screenshots in `artifacts/batch-30/`; and the reminder tests re-run explicitly against scratch Postgres (7 passed) because they skip without `DATABASE_URL`.

### Key facts for future sessions
- The coupon lives at `/leagues/:slug/predictions[/coupon|/results|/football]`. Build every link
  with `predictionsPath(slug, section)` from `lib/leagues.ts` — never a literal. It takes
  `string | null`, and `null` yields the slug-less path, which is the honest address while no
  league is bound (loading, or a member in none).
- **The URL binds the context, not the reverse.** `useRouteLeague()` returns `{slug, name}` and
  calls `selectLeague` on arrival; `activeSlug` is now only the default for an address naming no
  league. Batch 29's `LeagueSwitchStrip` effect was removed as part of this, so any *new* page
  under `/leagues/:slug/*` must call the hook or it will not bind — `LeaderboardPage` was switched
  to it for exactly that reason.
- Nav highlighting is deliberately slug-agnostic (`isCouponPath` / `isFootballPath` /
  `isLeagueHubPath`), against the BUILD_PLAN row's wording. Two reasons: a prefix built from the
  bound slug flickers off for a frame when tapping into another league, and `/leagues` would
  otherwise match the coupon and light the Leagues tab too.
- `MissingPickMember` carries `league_slug`, and the reminder sends
  `data.url = /leagues/{slug}/predictions` — the payload key `sw.ts` reads, which fell back to `/`
  before. Its body now formats `gameweek.locks_at_utc` in the member's timezone as `Sat 14:30`;
  anything re-hardcoding a lock time is wrong for a league not locking Saturday.
- The e2e harness needs `FRONTEND_ORIGIN=http://127.0.0.1:4173` (CORS allows exactly one origin)
  and one process must hold the `pgserver` handle for the whole run — the socket dies with the
  process that started it. A stale `uvicorn` on port 8000 will silently answer for a new one
  against a deleted database; check `lsof -ti tcp:8000` when the seed 500s.
- `docs/agent-commands/batch-verify.md` still names app-starter's venv for mypy/pytest. Use
  `scripts/ci-local.sh` instead, per the managed-venv rule — the doc is stale, not the rule.

**Next:** Batch 31 — Settlement cost per league.

## Batch 31 — Settlement cost per league
**Commits:** `2107dd9` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build, Playwright prod-bundle deep-link smoke. Run twice, before and after the commit.

### Key facts for future sessions
- **Settlement is now one provider read per run, not per round.**
  `settle_gameweeks_via_provider(db, provider, gameweeks)` de-duplicates every settleable
  round's outstanding fixtures, calls `provider.settle` once, and fans the settlements back
  out — `settle_gameweek` already ignores settlements its own picks don't reference. Anything
  that settles a round at a time re-introduces the per-league bill.
- `pending_event_ids` changed shape: it takes a *sequence* of rounds and returns
  `{gameweek_id: [event_id]}`. `settle_gameweek_via_provider` still exists as the plural over
  one round (`e2e_server.py` and the Batch 4 e2e slice use it), so there is one implementation.
- The dedupe works because a fixture is one pooled row since Batch 14 — two leagues holding the
  same match report the same `provider_event_id`. If fixtures ever stop being pooled, this
  collapses back to a per-league cost silently.
- **Step 2 of the row was not done and is not a defect.** Whether `/events` for a whole window
  carries `scores` for finished fixtures is unverified — it needs a live odds-api call and there
  is no key in the working tree. The open question is recorded on `OddsApiProvider._event_by_id`.
  Confirming it would turn a Saturday into one request per window instead of one per fixture.
- Running out of provider quota is **silent**: no error, picks just stay `pending` and the week
  never finishes. `_RecordingFake` in `test_scheduler_jobs.py` records what each `settle` call
  asked for, because that list is the bill — assert on it, not on wall-clock behaviour.
- `tests/test_football_router.py::test_an_anonymous_caller_is_refused` fails under app-starter's
  venv (401 vs the pinned FastAPI's 403). That is the documented pin divergence, not a
  regression — use `scripts/ci-local.sh`, which builds the pinned venv.

**Next:** Batch 32 — Per-league notification preferences.

## Batch 32 — Per-league notification preferences
**Commits:** `88d3a78` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build, Playwright prod-bundle deep-link smoke.

### Key facts for future sessions
- The mute flag lives on `league_memberships.notification_muted` (migration `013`), not a new
  table — that row already dies with the membership, so leaving and rejoining a league never
  inherits a stale mute.
- `members_missing_picks` filters muted memberships out at the query, so a muted league is never
  targeted rather than targeted and suppressed — `send_pick_reminders`' return count stays honest
  about who was actually nudged.
- `global_mute` and quiet hours are unchanged and still layered on top: the per-league flag
  decides whether a reminder is *wanted*; the user-level gate decides whether *now* is a good time.
- `GET`/`PATCH /api/v1/notifications/preferences` gained a `leagues: [{league_id, league_name,
  muted}]` list and a `PATCH` `league_mutes: {league_id: bool}` field — one settings read/write
  still serves the whole card. `PATCH` only touches memberships the caller actually belongs to.
- This closes the last open batch (1-33 are now all shipped on `main`); the only remaining build
  work is launch phase L5.

**Next:** Launch phase L5 — Launch and first-Saturday watch.

## Batch 34 — Switching league without leaving the coupon
**Commits:** `f97aa2b` (scoped in `6244575`) · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build (39 files / 314 tests), Playwright prod-bundle deep-link smoke. Run twice: after implementation and again against the exact tree committed. Frontend-only batch.

### Key facts for future sessions
- `leagueSwitchPath(slug, pathname)` in `lib/leagues.ts` is the whole rule: a league switch keeps
  the reader on the surface they are on. `LeagueSwitchStrip` derives it from `useLocation()` rather
  than taking it per call site, so a league-scoped surface added later is switchable without
  touching the component or its five mount points.
- **It takes a pathname and returns a path, and that is the `?gw=` guard** — structural, not
  remembered. A gameweek id is league-scoped and `resolve_gameweek` 404s on a foreign one, so
  "preserving state" across a switch would land on the empty state. Anyone widening the signature
  to a `Location` reopens the bug.
- Non-coupon surfaces fall back to the leaderboard deliberately, not lazily. A blanket slug-swap of
  the pathname is the tempting general form and is wrong: it carries a foreign player id into
  `/leagues/:slug/players/:id` and assumes admin of the target on `/admin/*`.
- The four `/admin/*` pages now call `useRouteLeague`, which pulls in `LeagueContext` — so their
  test harnesses need `LeagueProvider`. In `LeagueSettingsPage.test.tsx` the `/leagues/mine` matcher
  must sit **before** `/api/v1/leagues/[^/]+$`, which also matches it; serving a league *detail*
  where the context expects an array throws inside `activeSlug` on `leagues.some`, nowhere legible.
- Assert destination, not presence. `findByTestId('league-switch-strip')` was the only assertion
  either coupon test made, which is exactly how the leaderboard destination survived Batches 29 and
  30 — both aimed at this area.
- Two gaps left open on purpose: the leaderboard branch is covered in `leagues.test.ts` only (no
  `LeaderboardPage.test.tsx` exists and a harness for one href was disproportionate), and there is
  no browser check — it needs a two-league authenticated session, which `coupon-flow` does not seed
  and the prod-bundle smoke never reaches.

**Next:** Batch 35 — A one-off round in a multi-league game (current-round semantics, the ad-hoc rate limit sitting above the provider quota, narrowing the ad-hoc fetch by competition selection, and the never-refreshed one-off). Then launch phase L5 — Launch and first-Saturday watch.

## Batch 35 — A one-off round in a multi-league game
**Commits:** `9c85983` (scoped in `8910af3`) · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff check/format, mypy, `alembic upgrade head` + pytest on scratch pgserver, deployment-config assertions, pnpm lint/typecheck/test/build (39 files / 315 tests), Playwright prod-bundle deep-link smoke. Run twice: after implementation and again against the exact tree committed. 17 new tests (11 `test_scheduler_jobs.py`, 3 `test_request_budget.py`, 2 `test_picks_flow.py`, 1 Vitest).

### Key facts for future sessions
- `current_round_order(now, today)` in `services/gameweek.py` is the single definition of "the
  round a league is on", returned as ORDER BY clauses because it has two call sites that must move
  together: `latest_gameweek` per league, and the window function in `routers/me.py`. Home renders
  every league's card side by side, so a disagreement between them is visible in one glance.
  `accepting_picks(now)` is the SQL twin of `pick_refusal` — same three conditions, same order.
- **The "locking soonest" tiebreak is the rule, not decoration.** Two rounds open at once is the
  ordinary state, not the Boxing Day edge case: the 2-week discovery horizon plus a Batch 27
  pick-open offset produces it every week. Reordering by `starts_on` again would look harmless.
- **The budget comment in `config.py` overstates the saturated day.** It models ~420 requests of
  browsing; `test_request_budget.py` *measures* 336 (+60 discovery), leaving 104/day and 72/hour.
  `AD_HOC_GAMEWEEK_LIMIT = "2/hour;3/day"` is derived from the measured figures, and both caps are
  load-bearing — hourly alone permits 24x its number across a day, daily alone permits all of it
  inside the peak browsing hour. slowapi parses the `;` form into two enforced limits.
- `fetch_slate`'s `competition_ids` may only narrow a fetch **nobody shares**. `refresh_slate`
  (one production caller, the ad-hoc endpoint) passes it; `discover_fixtures` must not, because its
  fetch feeds every league on the window — narrowing there would deny the next league its fixtures.
  The two directions are asserted against each other in `test_scheduler_jobs.py`, on requests
  issued rather than rows written, since the rows were already right.
- `discover_fixtures` walks cadence dates **union** `unlocked_round_dates`, and syncs an off-cadence
  date only to leagues that already hold a round on it — otherwise a neighbour sharing the window
  has a Boxing Day round invented for it. `run_refresh_slate`'s horizon of 1 means a one-off is
  reached only in its final week, which is when postponements matter.
- The batch scope said the frontend was covered by existing surfaces; it was not.
  `useGameweekHistory` anchored `GameweekNav` on `gameweeks[0]`, correct only while the API's
  default *was* the newest `starts_on`. Both coupon surfaces now pass the id their own read
  resolved to, and `isLatest` means "no `gw` parameter" rather than "index 0".
- `_open_sample_gameweek`'s lock now moves with `weeks_later`. It was flat, which no test could see
  while "current" meant newest date and which makes the new rule untestable.

**Next:** Launch phase L5 — Launch and first-Saturday watch. All 35 build batches are shipped on `main`.

## Batch 36 — The odds key in the production logs
**Commits:** 7c4c1c4 (specs), 70e30e8 · verified: pinned ruff 0.5.4 check + format, mypy (59 files), pytest 425 passed/117 skipped, web lint/typecheck/build/test (315 passed)

### Key facts for future sessions
- **The exposed key still needs rotating — that is an owner action and this batch does not do it.**
  The code only stops future requests republishing it. Until rotation, the key in the retained
  Railway log window is live.
- Redaction happens in `_redacting_json_renderer` (`logging_config.py`), not at any call site.
  That is deliberate: it covers the event message, keyword values, nested structures, and any
  third-party library, and it survives someone re-enabling a quieted logger. `Settings.secret_values()`
  feeds it, sorted longest first so a secret containing another as a substring cannot be partially
  masked, and excluding values under 8 characters so an unset `""` cannot rewrite every line.
- `run_scheduled.py` never calls `configure_logging`, so one-off `railway run` jobs get stdlib
  defaults (WARNING) and neither leaked nor gained redaction. Left alone as out of scope, but a
  log level set there later would be unprotected — the redactor only guards configured processes.
- **The shared venv's ruff disagrees with the pin and will report a false failure.** It flagged
  `src/models/league.py` as unformatted; pinned ruff 0.5.4 reports all 94 files clean.
  `docs/agent-commands/batch-verify.md` says to use `uvx "ruff==$(...)"` for exactly this reason —
  the venv's ruff is not the gate and its formatting verdict should be ignored.
- The odds-api.io header question the batch row raised was **not** probed and no longer blocks
  anything: the renderer-level redactor already delivers what a header would have (survival past a
  re-enabled logger), so spending a live request to confirm it was not worth the quota.

**Next:** Batch 39 — Six admin buttons beside a title.

## Batch 39 — Six admin buttons beside a title
**Commits:** de5b3a6 · verified: pinned ruff 0.5.4 check + format, mypy (59 files), pytest 425 passed/117 skipped, web lint/typecheck/build/test (319 passed, +4)

### Key facts for future sessions
- **A member deliberately keeps a plain `Leave` button; only an admin gets the menu.** One
  button beside a title never overflowed, so collapsing it would cost a tap and save no width.
  The header therefore renders differently by role, which is intended rather than an oversight.
- The existing `ui/dropdown-menu.tsx` Radix primitive was already in the repo and unused by this
  component. It supplies focus management, Escape-to-close and outside-click dismissal, which is
  the substance of the batch — a row of buttons needed none of them.
- `DropdownMenuItem asChild` around a `Link` renders the anchor **as the menuitem**, so the items
  are `getByRole('menuitem')` and still carry `href`. Tests that looked for
  `getByRole('link', …)` no longer match; that is what the old admin test asserted.
- Radix's dropdown needed **no** jsdom shims here (no `hasPointerCapture`/`scrollIntoView`
  stubbing) — `userEvent.click` on the trigger opens it as-is. Worth knowing before adding
  polyfills to `test/setup.ts` for a future Radix component.
- `PageHeader.tsx`'s `min-w-0 max-w-full` action wrapper from Batch 22 was left alone. It is
  harmless with a single trigger and still correct for other pages using the slot.
- Not browser-verified: the component only renders for a signed-in league admin, and reaching
  that state needs credentials. Behaviour is covered by unit tests (collapsed, opened, Escape +
  focus return, and the delete dialog still gating deletion).

**Next:** Batch 38 — When a pick was taken.

## Batch 38 — When a pick was taken
**Commits:** 979a3bb · verified: `scripts/ci-local.sh` PASS (11 checks), including alembic upgrade head + the DB-backed pick flow

### Key facts for future sessions
- **Adding a timestamp changed what "distinct holder" means.** `_holders_by_fixture` deduped on
  the whole holder value, which was equivalent to per-player only while that value was
  `(player_id, name)`. Two selections claimed a minute apart are different values but the same
  person, so the fixture line would have named them twice. It now dedupes on `player_id` and
  keeps the **earliest** claim. Any future field added to `_Holder` faces the same trap.
- `taken_at` is **additive and optional on the client** on purpose. Vercel deploys the web app
  from `main` while the API waits for `/ship-prod`, so a renamed or required field would break
  the coupon in the gap. `types.ts` marks it `?` and `PickCard` renders the holder's name with
  no time when it is absent — there is a test for exactly that.
- The time is **absolute**, in the league's timezone, formatted `d MMM, HH:mm` — the kickoff
  line's format minus the weekday. Relative ("2h ago") was rejected: the coupon is cached, so a
  relative label is wrong as soon as it is re-read without a re-render, and a pick window that
  opens weeks ahead makes a bare weekday ambiguous.
- Only the **per-selection** line carries the time. The fixture-level `Picked by …` summary was
  left as names: it is a summary of *who*, and duplicating the instant there reads as noise.
  This is a deliberate narrowing of the batch row, which asked for both.
- **Every instant this API returns is naive UTC** (`DateTime(timezone=False)` on `created_at`,
  `kickoff_utc`, `locks_at_utc`) and serialises without a `Z`, while the frontend parses with
  `new Date(...)`, which reads a bare string as *local*. `taken_at` was made consistent with its
  siblings rather than diverging. Worth noting that the app-wide convention means displayed
  times are off by the local UTC offset for any non-UTC viewer — pre-existing, not this batch.
- `scripts/ci-local.sh` is the gate that actually exercises the pick flow; a bare `pytest` skips
  41 DB-backed tests silently, so a green plain-pytest run proves less than it looks.

**Next:** Batch 37 — A division that resolves to the Premier League.

## Batch 37 — A division that resolves to the Premier League
**Commits:** 42be031 · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The tab is still empty after this ships, and that is expected.** The code no longer
  mis-resolves, but production already holds rows written under the wrong id: `upsert_teams`
  moves a club's `competition_id` to wherever it was last seen, so Premier League clubs and
  tables sit against non-League competitions and genuine clubs may have been dragged out of
  correctly-matched ones. **The affected competitions' teams and standings must be cleared
  before a corrective `sync-football` sweep.** That data work was deliberately excluded from
  this batch and is still owed.
- **Coverage is not the problem and the Batch 33 question is closed.** A catalogue probe on
  2026-08-19 returned 1240 leagues, 46 English, 24 carrying season 2026, including National
  League North/South (50/51) and all four Non League Premier divisions (58/59/931/60).
- `similarity(..., allow_subset=False)` is the fix, not a lower `SUBSET_SCORE`. The bonus is
  load-bearing for clubs ("Inverness Caledonian" for "…Thistle"); lowering it there unmatches
  real clubs. One flag, two opposite truths — a shorter *club* name is an abbreviation, a
  shorter *competition* name is a different competition.
- `league_id_for` now applies `MATCH_MARGIN` as well as `MATCH_THRESHOLD`. It never did,
  despite `similarity`'s docstring saying the subset score leans on that guard — the guard
  lived only in `best_match`, which the competition path does not use.
- **An override answers before `_all_leagues()` is called**, so an overridden competition
  costs zero catalogue requests. Both sides of the four entries were read from the live
  odds-api.io and api-football catalogues on 2026-08-19, not inferred from a spelling rule.
  Slugs are odds-api.io's (`england-amateur-southern-league-premier-division-south`).
- The National League regional slugs are **absent from the override table on purpose** —
  they normalise to an exact match, and listing them would imply they were broken.
- The old `LEAGUES` test fixture had no "Premier League" row, which is why no test caught
  this: the wrong answer was not in the candidate list. `ENGLISH_PYRAMID` now mirrors the
  real catalogue, and the regression test asserts `!= "39"` explicitly.
- Nothing was needed on the frontend. `PickCard` has rendered position and form since Batch
  16 and hides the strip only when a club has neither.

**Next:** Batch 41 — Naming the round.

## Batch 41 — Naming the round
**Commits:** 72bdae8 · verified: `scripts/ci-local.sh` PASS (11 checks), including migration 014 on a clean scratch database

### Key facts for future sessions
- **The number is stored, not derived, and Batch 35 is why.** An ordinal computed from
  `starts_on` order renumbers every later round the moment an admin inserts a one-off, so a
  member's "Gameweek 12" silently becomes a different week. Stored, a one-off takes the *next*
  number — it is the next round the league plays — and history is fixed. Do not "simplify" this
  back into a derived ordinal.
- Numbering is **one past the maximum**, not one past the count, so deleting a round leaves a
  gap rather than handing its number to the next round. Per league, per season.
- **No unique constraint exists and none can, cheaply.** The season a number is unique within is
  derived from `starts_on`, not stored, so the invariant lives in `next_gameweek_number` alone.
  Adding a `season` column purely to constrain it was judged not worth a column nothing reads.
- Migration 014's season expression is **duplicated SQL**, not an import — a migration must not
  depend on application code that keeps moving. `test_migration_014` is what holds the two
  definitions together; if `_SEASON_ROLLOVER_MONTH` ever changes, that test fails first.
- `DATE :param` is not valid SQL and asyncpg infers a bind's type from its cast — seeding a
  migration test needs real `date`/`datetime` objects passed as parameters, not strings cast in
  the statement. Cost two debugging rounds here.
- `number` is optional on **both** TS types and nullable in the API. The web app deploys ahead of
  the API, so a slate served before this ships has no number; `roundName` falls back to the date
  the round always showed. One helper serves the header and the nav so they cannot disagree.
- `roundName` tests `0` explicitly: `number || fallback` would drop a legitimate Gameweek 0.
- `GameweekNav` still hides below two rounds. That rule is about *navigation* having somewhere
  to go, not about naming — the header labels the round either way.

**Next:** Batch 42 — Profile pictures (code-only, no storage bucket).

## Batch 42 — Profile pictures
**Commits:** 531985a · verified: `scripts/ci-local.sh` PASS (11 checks), including migration 015 on a clean scratch database

### Key facts for future sessions
- **Avatars are modelled but not enabled, and uploading answers 503 in every environment.**
  `AvatarStorage` has exactly one implementation — `UnconfiguredAvatarStorage` — which refuses
  writes and no-ops deletes. `src/services/avatar_storage.py` lists the three things that must
  be true before a backend is wired; the outstanding one is that **bytes are never re-encoded**.
  Magic-byte sniffing proves a header, not a payload, and no imaging library is a dependency.
- The image is the **raw request body** typed by `Content-Type`, not multipart. Deliberate: one
  file needs no envelope and it keeps `python-multipart` off the API's dependency list. The
  client sends `fetch(url, {method:'POST', headers:{'Content-Type': file.type}, body: file})`.
- `_read_capped` streams and aborts past the cap rather than `await request.body()`, so an
  oversized upload is refused while it arrives instead of being buffered whole first.
- **Removal is a *site* admin action, not a league admin one.** An avatar is a profile field and
  follows a member into every league, which reaches past any single league's remit. Clearing
  your own works whether or not a backend exists, so enabling one is not a one-way door.
- `AvatarUpload.tsx` is **built and intentionally unmounted**. A visible control that always
  fails is worse for members than none; the component's docstring says exactly where it mounts
  (`SettingsPage`, a `SectionCard` beside Timezone) when a backend lands.
- The display half needed no work — `AuthContext`, `TopBar` and `LeagueMembersPage` already
  passed `src` to `Avatar`. It was null only because the API hardcoded it.
- **`MagicMock(spec=Profile)` returns a mock for any unset attribute**, and pydantic rejects
  that against `str | None`. Adding a field to `PlayerInfo` therefore breaks every auth test
  until `_make_user` sets it. Expect this again for the next profile field.
- **A deprecation warning from the shared venv can be a trap.** Newer starlette warns that
  `HTTP_413_REQUEST_ENTITY_TOO_LARGE` is deprecated; following that advice raises
  `AttributeError` on the pinned starlette==0.37.2 that CI and production run. Same class of
  divergence `batch-verify.md` records for ruff — trust the pins, not the dev venv.

**Next:** No unchecked build batches remain except Batch 40 (deferred pending a product decision).

## Batch 43 — Every time this app shows is an hour wrong
**Commits:** 29b2104 · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The fix is one annotation, `UtcDatetime` in `apps/api/src/schemas.py`**, applied to every
  datetime a response model carries. It is a `PlainSerializer` returning an *aware* datetime,
  not a string, so OpenAPI still says `format: date-time` and a Python-mode `model_dump()`
  still yields a `datetime`. Pydantic renders that as `…Z`, not `+00:00` as the row's wording
  suggested — same instant, and it needs no bespoke string serialiser.
- **`tests/test_wire_datetimes.py` walks `app.routes` and the models they nest**, so a model
  written next year is covered the day it is added. Proven to bite: reverting one field to a
  bare `datetime` fails it naming `CurrentRound.locks_at_utc`. Storage stays naive UTC — no
  migration, no column change, and the backend's naive-to-naive comparisons are untouched.
- **The test runner's zone is now pinned to `America/New_York` (`vite.config.ts`).** This is
  the load-bearing half of the frontend work: in a UTC process a mis-parsed instant and a
  correct one are the same number, so CI (UTC) could never see this while this Mac
  (Europe/London) could. Do not "simplify" that env line away.
- The frontend fixtures now carry the **offset-less** shape the API really sends, not the
  `Z` form they were written with. Some `created_at` fixtures still use `Z` — deliberately:
  both shapes are live at once during the ship gap.
- The client keeps its own defence (`parseInstant` in `src/lib/time.ts`) even though the API
  is fixed, because Vercel deploys `main` on merge and the API waits for `/ship-prod`.
  **Until that ship-prod runs, the client-side half is the only half in production.**
- **`starts_on` is a calendar date, not an instant.** `new Date('2026-08-22')` is UTC
  midnight, so `formatInTimeZone` into any American zone rendered the previous day — the
  round announced for a Friday. `formatCalendarDate` renders the day it names and converts
  nothing. `GameweekNav`, `ResultsPage`, `PlayerProfilePage` and `CouponCombinedPage` no
  longer take a `timezone` prop at all.
- Reverting `parseInstant`/`formatCalendarDate` fails **14 tests across 4 files**, including
  three that predate this batch — that is the regression gate, and it did not exist before.

**Next:** Batch 44 — Turning avatars on.

## Batch 44 — Turning avatars on
**Commits:** 4d1d665 · verified: `scripts/ci-local.sh` PASS (11 checks), venv rebuilt from the new pin

### Key facts for future sessions
- **The feature is complete and switched off.** `AVATAR_STORAGE` defaults to `none`, so every
  environment behaves exactly as it did after Batch 42 — 503 on upload, no card in Settings.
  Turning it on is `docs/runbooks/avatar-storage.md`, and it is an **owner action**: it needs
  the Supabase dashboard and seals a service-role key. Nothing was provisioned by this batch.
- **Pillow is the API's first imaging dependency** and pinned to the newest patched line on
  purpose — it is the one dependency here whose whole job is parsing bytes a stranger chose.
  `ci-local.sh` rebuilt its venv from the changed pin and passed, so the manylinux wheel
  resolves; nixpacks installs from the same file.
- **The bomb guard is an ordering, not a check.** `Image.open` parses the header only, so
  dimensions are known while refusing is still cheap. The 2 MB body cap bounds what *arrives*
  and says nothing about what a decoder allocates — a 4000×4000 1-bit PNG is under 100 KB.
  Do not move the pixel check after the decode.
- **`avatar_url` is a plain public URL and the random key is the access control** (ADR 0006).
  Player ids are on every league page, so a key derived from the id alone would make every
  member's picture enumerable. Replacing a picture deletes the old objects, which is what
  makes `immutable` caching safe and what makes a leaked URL stop resolving.
- Private-bucket signed URLs were the stronger posture and were rejected on cost: the column
  becomes a path and every member list becomes a Supabase round trip per picture. The owner
  accepted the trade-off on 2026-08-20.
- **`GET /api/v1/config` is read live, never cached at login.** It was deliberately *not* put
  on `PlayerInfo`: the client stores that at login and refreshes it only on the next one, so
  a member signed in before the bucket existed would carry a stale `false` indefinitely.
- A 404 from `/api/v1/config` must read as "feature off", not as an error — Vercel ships this
  app from `main` on merge while the API waits for `/ship-prod`, so the route is genuinely
  absent for a few days. `useClientConfig` has `retry: false` and falls back to all-off.
- **A test fixture whose catch-all returns 401 will tear down the page's auth.** Adding the
  `/config` call to `SettingsPage` broke four unrelated tests that way before the fixture
  answered the route explicitly. `apiFetch` treats 401 as an expired session and redirects.

**Next:** Batch 45 — A sweep that fails completely and reports success.

## Batch 45 — A sweep that fails completely and reports success
**Commits:** 8f72d0d · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **A list of reports cannot answer the job's question**, and that is the whole batch. A
  competition that *raised* leaves no report, so an empty list means both "the card was
  empty" and "all 21 failed" — opposite verdicts. `FootballSweep` carries `attempted`
  alongside the reports because it cannot be derived from them.
- `carried_nothing` is `attempted > 0 and carried == 0`. One condition covers **both**
  shapes of total failure — every competition raising, and every competition being
  honestly empty — because `carried` counts reports and a raiser has none.
- **The sweep's per-competition tolerance was not touched and must not be.** One division
  the provider dropped must not cost the other twenty-nine their tables. The verdict is
  the caller's job; that separation is the design, not an accident.
- Both legitimate zero-work runs stay green and are tested: no provider configured
  (returns before a sweep starts) and an empty fixture pool (`attempted == 0`). Batch 16's
  docstring warns against exactly the regression of failing an opted-out deployment daily.
- **A card where every competition genuinely has nothing yet would now be called a
  failure.** Accepted deliberately: across twenty-odd British divisions that is not a
  state that lasts, and a morning where nothing at all could be ingested is worth
  surfacing.
- The partial-failure threshold the row suggested (18 of 21 raising is not healthy) was
  **not** implemented — the row says the total-failure case should not wait for agreement
  on a ratio. The log line now carries `attempted`, `reported`, `failed` and `carried`, so
  whoever wants a ratio has the data.
- `backfill_season` got the same verdict and the same return type. Same defect one
  function away, and a human reads that one's output.
- `run_scheduled.main` already maps `False` to `SystemExit(1)`, so the cron became honest
  with no change there — `test_main_exits_nonzero_when_job_fails` already covered it.
- Reverting the verdict fails two scheduler tests, and the log output they print is the
  literal production line: `football data synced attempted=21 carried=0`.

**Next:** No unchecked build batches remain except Batch 40 (deferred pending a product
decision). Launch L5 — launch and first-Saturday watch — is the remaining launch work.

## Batch 40 — A round the pick window never reached
**Commits:** 15d3b3a · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The forward-only rule stands, and the admin restamp was deliberately not built.** The
  row's own 2026-08-20 production read settled it: `the-coupon` had all three rounds at
  `picks_open_at_utc = NULL`, only the 08-22 round was affected, and it held zero picks.
  A one-round transitional problem does not justify standing machinery that invites the
  exact edit `leagues.py:873` forbids — moving a deadline members were already told.
- **What shipped is visibility, not behaviour.** No API change, no migration; both instants
  already rode on `GameweekListEntry`. `PickOpenSchedule` lists the rounds an opening can
  still apply to and says what each will actually do.
- **`picks_open_at_utc = NULL` means no gate at all — not an older offset.** `pick_refusal`
  gates only when the column `is not None`, so such a round is claimable from the moment
  discovery writes it. That is the case that reads as "my setting was ignored", so it is
  worded most plainly: "Open now — no opening time was set".
- Locked and settled rounds are excluded on purpose. Their opening is history, and showing
  it would invite the restamp this batch decided against.
- **Adding `useAuth` to `LeagueSettingsPage` broke all 9 of its existing tests at once** —
  the file's `renderPage` never wrapped `AuthProvider`, though the real app always does.
  Expect this for any page-level test harness here that has not needed the player before.
- `formReady()` is defined per-describe in that file, not at module scope; a new block
  needs its own. The barrier matters for the same reason Batch 27's note gave — the
  assertions that follow do not all retry.
- `PickOpenSchedule` guards with `Array.isArray` rather than trusting its prop. The web
  app deploys ahead of the API, and a settings page that throws is worse than one that
  shows nothing.

**Next:** No unchecked build batches remain. Launch L5 — launch and first-Saturday watch.

## Batch 46 — Reading the whole card from a source that has it
**Commits:** beb070b · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **Probe before you trust ADR 0007's coverage claim.** It was written as settled with
  only the *tables* checked; `fetch_results` — half the port, and the source of the pick
  card's form strip — was never verified. The probe closed it and changed the design.
- **One request returns both halves.** `/api/data/leagues?id=X` carries `table` *and*
  `fixtures`. The ADR assumed api-football's two-per-competition shape. `fetch_table`
  and `fetch_results` share one memo, so `8947`'s four competitions cost one request.
- **Tables split; results do not.** A composite payload has `data.tables` with a
  `leagueId` per division. `fixtures.allMatches` is flat — 1104 matches for `8944` —
  with **no** division marker on a match. Do not go looking for one; `round`/`roundName`
  are matchweek numbers.
- **Attribution is by team id, never by name.** Table rows carry integer ids, giving a
  team-id → division index. Live measurement: 1104/1104 and 67/67 attributed, and 67/67
  finished matches had both teams in the same division. Removing the filter fails
  `test_results_are_attributed_by_team_id_not_by_name`.
- **Country-scoping is load-bearing, not tidiness.** Name-only matching put Scotland's
  League One on England's `108`, Scotland's Championship on England's `48`, and
  Scotland's Premiership on Northern Ireland's `129` — against the live catalogue. Same
  class as Batch 37. odds-api.io says "England Amateur", so the trailing word is stripped
  before the country lookup.
- **Group ids, read live on 2026-08-20:** `8944` → 940360 NL North, 940374 NL South;
  `8947` → 941117 Southern Central, 941118 Southern South, 941116 Northern Premier,
  941109 Isthmian; `9545` → 1000001473 Highland, plus both Lowland groups we do not use.
- **A 404 must raise.** `/api/leagues?id=47` 404s while `/api/data/leagues` works; a
  swallowed 404 would turn a path change into a silent empty sweep, which is exactly what
  Batch 45 exists to catch.
- Recorded payloads live in `tests/fixtures/fotmob_payloads.json` — **full** table rows,
  because trimming them to three per group emptied the division index and made the
  attribution test vacuous.
- Ships dark. `FOOTBALL_DATA_PROVIDER` still defaults to `none`; `fotmob` needs no key.

**Next:** Turning it on is one variable plus a staging sweep. Launch L5 remains.

## Batch 47 — A league with no rounds until tomorrow morning
**Commits:** `f03a6bb` · verified: `scripts/ci-local.sh` PASS (11 checks) — 635 pytest
with a database (499 without), Ruff 0.5.4 check/format, strict mypy, clean `pgserver`
through `015`, 355 Vitest, Node 20 build, prod-bundle Playwright; plus a live browser
run against `tests/e2e_server` on a scratch Postgres

### Key facts for future sessions
- **The pool *is* the second entry point.** `discover_fixtures` already fetches each
  `(window, date)` once, so `pooled_slate` turns existing `fixtures` rows back into a
  `Slate` — same `query_bounds` in SQL, same `contains` in Python — and `sync_slate`
  cannot tell it from a fetched one. The common case costs **zero** provider requests.
  Caveat worth knowing: a date whose only fetch was an ad-hoc one holds just that
  league's competitions, so a pooled read can be a partial card. The daily run heals it.
- **Sharing a slowapi limit needs both halves.** `slowapi` evaluates a limit as
  `limiter.limiter.hit(item, key, scope)` with `per_method=False`, so a route decorated
  `shared_limit(value, scope)` and `consume_shared_limit(key, value, scope)` draw one
  bucket. The imperative half exists because a decorator charges every request that
  reaches the route, and charging the free pooled case would price the common one out.
- **The bucket counts sweeps, not calls.** One unit ≈ one league-scoped `/events` sweep
  (≤30 requests), charged per *date* the pool cannot serve. With `slate_horizon_weeks=2`
  an unpooled league spends the whole `2/hour` in one refresh — which is what keeps
  `PROVIDER_SLATE_FETCH_LIMIT`'s arithmetic true however many routes spend it.
- **`create_league` must not resolve `OddsProviderDep`** — it raises 503 when the
  provider is unreachable, which would wire creating a league to odds-api.io being up.
  New `get_optional_odds_provider` returns `None` instead; tests overriding the provider
  must override **both** functions (`test_picks_flow`, `e2e_server`) or creation silently
  reaches the real session.
- **The window is the filter, so moving it changes which pooled fixtures qualify.** A
  refresh after a window move links the new window's fixtures and keeps the old ones —
  `sync_slate` adds links and never removes them — while `picks_open_at_utc` and
  `locks_at_utc` stay as stamped. A test that pools fixtures only at the *old* time and
  then moves the window will see a fetch, not a rebuild; that was a real red.
- **A fetch that found nothing is not "nothing to do".** The live run exposed a false
  toast: the endpoint swept both cadence dates, the provider carried no card for either,
  and the UI said "Rounds are already up to date". `fetched_dates` non-empty with zero
  rounds is the ordinary out-of-season answer and now says so.

**Next:** Batch 48 — the pick screen dies when the odds provider says no. This batch is
API-side, so it is invisible in production until a `/ship-prod` runs.

## Batch 48 — The pick screen dies when the odds provider says no
**Commits:** `1f16873` · verified: `scripts/ci-local.sh` PASS (11 checks) — 647 pytest
with a database (508 without), Ruff 0.5.4 check/format, strict mypy, clean `pgserver`
through `015`, 357 Vitest, Node 20 build, prod-bundle Playwright

### Key facts for future sessions
- **The fallback lives behind the port, not in the router.** `fetch_odds_best_effort`
  returns `OddsSnapshot(odds, degraded)` and never raises: the base implementation on
  `OddsProvider` degrades to *no* prices, and `CachingOddsProvider` overrides it to serve
  the entries it is already holding past their TTL. `fetch_odds` is untouched and still
  raises, which is the whole of "browsing degrades, picking must not" — the two
  request-path callers get opposite treatment without the router knowing which provider
  it holds.
- **A failed refresh must not restamp the entries**, or recovery would wait a full TTL
  instead of a page load. The corollary is that a degraded slate re-attempts upstream on
  *every* load (one chunked sweep each). Fail-fast on `429` is what makes that
  affordable; no failure cooldown was added, and that is the thing to reach for if a
  long outage ever proves it needs one.
- **A FastAPI dependency override must close over its instance, never take a default
  argument.** `lambda cached=CachingOddsProvider(...): cached` is read as a *query
  parameter*, and pydantic deep-copies the default per request — so every request got its
  own empty cache and the warm-cache test proved nothing while appearing to pass. That
  cost a red before it was spotted.
- **`429` is now terminal in `OddsApiProvider._get`.** `betfair.py` and `api_football.py`
  still retry it — deliberately out of scope, and neither is the production odds source.
  Settlement inherits the change: a rate-limited settle run now fails on its first
  attempt and waits for the next scheduled tick rather than spending 4x the quota to
  fail anyway.
- **The pick submit path answers `503 ODDS_UNAVAILABLE`** where an unreachable provider
  used to be an unhandled 500. Still a refusal, still loud, but one the client can name —
  `pickErrorMessage` says the pick was *not saved*, which a generic error did not.
- **app-starter's venv can no longer run this suite.** It has no Pillow, so ten test
  files fail at collection through `avatar_storage.py`, and it ships fastapi 0.139
  against the pinned 0.111. `scripts/ci-local.sh` (venv at `~/.cache/the-coupon/`) is the
  real gate; `AGENTS.md` and `docs/agent-commands/batch-verify.md` still document the old
  path and are wrong.

**Next:** no unchecked batches remain in `docs/BUILD_PLAN.md`. Launch L5 — launch and
first-Saturday watch — is the remaining work. This batch changes both halves, so the web
banner deploys on merge while the API fallback waits for a `/ship-prod`; until then the
flag is simply absent and the client reads that as "not degraded".

## Batch 49 — A postponed fixture nobody can take off the card
**Commits:** `d1a95d4` · verified: `scripts/ci-local.sh` PASS (11 checks) — 652 pytest
with a database, Ruff 0.5.4 check/format, strict mypy, clean `pgserver` through `015`,
357 Vitest, Node 20 build, prod-bundle Playwright

### Key facts for future sessions
- **The provider's answer was neither of the two the plan anticipated, and this matters.**
  Probed live 2026-08-21: `/events` *does* carry a status and *does* emit void words — 2
  of the 1,599 fixtures listed for 2026-08-22 came back `cancelled` — but Hibernian v
  Kilmarnock, the fixture that prompted the batch, was still `pending` despite being
  called off. So the general case is closed and the observed one is not. Do not expect
  pre-lock removal to catch every postponement; settlement's `void` is still the backstop.
  api-football cannot second-opinion it — the free plan refuses any 2026-season query.
- **`SlateFixture.status` defaults to `""` and that default is load-bearing.** It means
  "this source does not say", which is the truth for `FakeBetfair` (a catalogue of open
  markets) and for `pooled_slate` (rebuilt from `fixtures`, where no status is stored).
  Both therefore *cannot* unlink anything, which is what keeps a pooled refresh and an
  ad-hoc rebuild safe without either of them knowing about Batch 49.
- **Removal is gated on `locks_at_utc`, never on `GameweekStatus`.** The label is only
  what the hourly jobs keep up with; the instant is the fact. A test dated in the past
  would therefore pass for the wrong reason, which is why `_upcoming_saturday()` derives
  a date from `uk_today()` rather than reusing `SAMPLE_SATURDAY` (2026-08-01).
- **`gameweek_fixtures` has no cascade to `picks`** — it is a composite-key join, and
  `Pick` references `fixtures`/`gameweeks` directly. Unlinking alone leaves a pick off
  the screen but still visible to settlement. Anything that removes a link in future has
  to delete the pick too.
- **The postponement notification lives in `services/gameweek.py`, not
  `notification_triggers.py`**, because that module imports this one
  (`members_missing_picks`) and the cycle is real. `data.type` is free-form, so
  `"fixture_postponed"` needed no enum and no migration; an `ActionType` would have.
- **Round creation now keys on the *playable* fixtures**, so a date whose whole card is
  called off produces no round rather than an empty one. Slightly wider than the row
  asked for, and the natural corollary of the rest.

**Next:** Batch 50 — the three omissions on the pick card. This batch is API-side, so it
is invisible in production until a `/ship-prod` runs; until then the deployed API keeps
carrying a called-off fixture on the card.

## Batch 50 — What the pick card leaves out
**Commits:** `e821d95` · verified: pnpm lint (0 errors), typecheck, build, 361 Vitest — all
green. Frontend-only batch (scope boundary: no API change), so the backend gate and
browser checks are out of scope.

### Key facts for future sessions
- **The names row and context strip are now one grid, not two.** `PickCard`'s team names
  used to be an inline sentence (`Home v Away`) sitting over a separate `grid-cols-2`
  strip below it — they aligned by text-length coincidence. Both rows are now children of
  the same `grid grid-cols-2` container, with the context cells wrapped in a
  `display: contents` div so the `fixture-context-{id}` test id still resolves to just
  those two cells.
- **The "v" separator is absolutely positioned but kept in DOM order between the two
  names**, not appended after both — otherwise a screen reader would announce "Home,
  Away, v" instead of "Home, v, Away".
- **`potentialPoints()` was already free to keep on-screen in every claim state** — it's a
  pure `round(odds × 10)` of the displayed price, so showing it on "taken by X" and "your
  pick" needed no new prop, just dropping the exclusive three-way branch in
  `SelectionButton`.

**Next:** Batch 51 — untying Football Stats from the coupon's league-competition scope.

## Batch 51 — Football Stats is not a coupon surface
**Commits:** `4d94888` · verified: `scripts/ci-local.sh` PASS (11 checks) — 655 pytest with
a database, Ruff 0.5.4 check/format, strict mypy, clean `pgserver` through `015`, 366
Vitest, Node 20 build, prod-bundle Playwright

### Key facts for future sessions
- **The screen's data was never league-scoped — only its read was.** `pooled_competitions`
  already walked the whole fixture pool and `teams` / `matches` / `standings` carry no
  league column, so untying it cost **zero** extra provider requests. Anything that looks
  league-scoped in the football half is worth checking against this before it is believed.
- **A competition is in the pool only if a `fixtures` row names it.** `pooled_competitions`
  derives from `fixtures.competition_id`, not from `standings`, so "every competition we
  hold" means every one some league's card has drawn from. That is what the empty states
  now say, and it is why `test_football_router.py` must seed `Fixture` rows — the old seed
  wrote standings alone and would return nothing at all against the new endpoints.
- **The pool is shared, so those tests assert containment, not length.** Every assertion
  filters the response to the run's own tagged slugs; `test_picks_flow` and
  `test_round_population` both commit fixtures that survive into this suite's view.
  `Match` is unique on `provider_match_id` globally and `sync_results` re-points
  `competition_id`, so a crashed run leaves no duplicate — only a moved row.
- **`isLeagueHubPath` now tests the predictions *shape*, not the section list.** Dropping
  `/football` from `PREDICTIONS_SECTIONS` made `predictionsSection()` return `null` for
  the retired addresses, which would have lit the Leagues tab for the frame before the
  redirect. Any future section removal has the same trap.
- **`scripts/check-deploy-drift.sh`'s tier-3 probe named the route this batch deleted.**
  Left alone it would have called a *current* image DRIFTED. Repointed to
  `/api/v1/football/tables` / Batch 51. Deleting a route means moving that probe.
- **"Football Stats" fits the mobile tab bar on one line** — measured against the built CSS
  in Outfit at 57.7px, in a 75px tab at 375px and a 64px tab at 320px. No wrap, no
  clipping, no CSS change needed. Roughly one more character of slack is all there is.

**Next:** Batch 52 — the Form column hidden on every phone, and results grouped by day
alone. This batch is API-side as well as web, so the two halves separate on merge: Vercel
takes the new `/football` screen immediately while the deployed API still serves only the
league-scoped endpoints, which the untied page does not call. **A `/ship-prod` is owed
before the tab works in production.**

## Batch 52 — A table that hides the column it exists to show
**Commits:** `6b1950c` · verified: pnpm lint (0 errors), typecheck, build, 369 Vitest — all
green. Frontend-only batch (scope boundary: no API change, both fields already served), so
the backend gate and browser checks are out of scope.

### Key facts for future sessions
- **Batch 51's "Next" note calling this batch API-side was wrong** — both `form` and
  `competition`/`competition_id` were already served on `CompetitionTable` and
  `ResultEntry`; nothing needed adding on the API side.
- **The narrow-width trade flipped, it didn't grow.** `LeagueTableCard` still hides four
  columns below `sm`, just not the same four: Goal Difference now carries `narrowHidden`
  and Form does not, since form is one of the two things a member opens the screen to read.
- **`groupByDay` now nests a `Map<competition_id, CompetitionGroup>` inside the day map**,
  so a Saturday across four competitions produces one heading per competition instead of
  one undifferentiated eighty-match list. The per-row competition label only survives when
  a day has exactly one competition, so a single-competition day doesn't grow a redundant
  second heading.
- **Precondition confirmed before starting: ingestion is still broken.**
  `run_sync_football_data`'s docstring ([scheduler.py:259](apps/api/src/scheduler.py:259))
  still records the 2026-08-20 all-competition failure; this batch improves the
  presentation of what may currently be an empty screen, and that's expected — no ingestion
  change was in scope.

**Next:** Batch 53 — form pips that open into the matches behind them.

## Batch 53 — Form you cannot open
**Commits:** `0235e9f` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff
check/format, mypy, alembic upgrade head + pytest on scratch pgserver,
deployment-config, pnpm lint/typecheck/test/build, playwright deep-link smoke. Plus
targeted runs: 16 football backend tests against a real `pgserver`, 66 Vitest across
`FormLine`/`PickCard`/`FootballPage`.

### Key facts for future sessions
- **The batch arrived already implemented, uncommitted, on an existing branch.** A prior
  session had left ~770 lines on `feat/batch-53-form-disclosure` with the row still
  unchecked. `/batch-start`'s clean-worktree-on-`main` precondition does not describe
  every real start; audit against the row before assuming a fresh one is wanted.
- **`docs/agent-commands/batch-verify.md` is still wrong and cost a full cycle again.** Its
  backend commands point at app-starter's venv, which has no Pillow (pinned since Batch
  44), so pytest dies at collection in ten files. `scripts/ci-local.sh` is the only
  correct gate; its venv is reusable at `~/.cache/the-coupon/ci-local-venv/bin/`. A task
  chip is open to fix the doc — this has now bitten Batches 48 and 53.
- **`league_tables()` no longer trusts `standings.form`.** It derives the string from the
  matches it just loaded (`form_string(recent) or standing.form`). The provider writes
  that string from a *different* upstream call and it can disagree with `matches`; once
  the pips open, a disclosure contradicting the thing that opened it is worse than none.
  The stored string survives only as the fallback for a club with a table line and no
  matches — pips the client deliberately leaves inert.
- **A disclosure cannot live inside `role="img"`.** That role swallows its subtree, leaving
  `aria-expanded` nothing to describe. `FormLine` keeps the role only while it is a plain
  graphic and moves the *same* accessible name onto a real `<button>` when `onToggle`
  arrives. The name did not need rewording — it names the same thing either way.
- **The panel is placed by the caller, never inside the pips.** In the table's Form cell it
  would have forced sideways scrolling and undone exactly what Batch 52's hidden columns
  protect; so the table opens a `colSpan` row and the pick card opens full-card-width
  under the header.
- **Results print oldest-first, against the usual results-list habit**, so the nth row is
  the nth pip. Reversing one list against the other to identify a pip is a puzzle, not an
  answer. Scores are for-and-against from the club's own side with H/A saying which end,
  which keeps them readable without colour — the same rule the pips follow.
- **Precondition still unresolved:** `run_sync_football_data`'s docstring
  ([scheduler.py:259](apps/api/src/scheduler.py:259)) still records the 2026-08-20
  all-competition sweep failure. On current production data these pips may open onto
  nothing anywhere. The degradation is correct (inert, no empty panel), but the feature
  cannot be judged live until ingestion is fixed.

**Next:** no unchecked batches remain — `docs/BUILD_PLAN.md` is complete through Batch 53.
Launch planning resumes at **L5 — Launch and first-Saturday watch**, the only open phase in
`docs/LAUNCH_PLAN.md`. This batch is API-side as well as web, so the halves separate on
merge: Vercel takes the client immediately while the deployed API still serves
`TableEntry` without `recent`. `TableEntry.recent` is optional precisely for that window —
table pips simply will not open until **a `/ship-prod` is owed and run**.

## Batch 54 — A palette that was only ever checked against two of its four surfaces
**Commits:** f31cfbf · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 660 (clean schema, 0 skips) · lint · tsc · build · vitest 425

### Key facts for future sessions
- `--text-muted` is now `#8690A6` (dark) / `#666F7D` (light). Both were chosen as the
  *smallest* change that clears 4.5:1 on all four surface tiers; do not nudge them
  back toward the old greys without re-running `src/test/contrast.test.ts`.
- **`accessibility.test.tsx` cannot see colour and never will.** jsdom will not resolve a
  CSS custom property, so axe's `color-contrast` rule is disabled there. That is why
  `contrast.test.ts` exists and reads `index.css` off disk instead — Vitest stubs CSS
  imports, so both a plain import and `?raw` hand back an empty string.
- Six contrast failures remain in light mode and are deliberate: `--primary` and
  `--warning` used as text. One value cannot fix them — as text on white a colour needs
  relative luminance ≤ 0.183, as a fill under `--on-primary` it needs ≥ 0.208. They need a
  brand-as-ink token distinct from brand-as-surface. `KNOWN_DUAL_ROLE_DEBT` in the test
  asserts that list is exactly right, so it cannot silently grow.
- `--locked` is defined in both palettes and referenced by **nothing** — 0 text, 0 fill,
  0 border uses. Kept in sync with `--text-muted` rather than deleted, but it is dead.
- The full review this came from is `docs/review/2026-08-22/`, and Batches 55-60 are
  specified from it.

**Next:** Batch 55 — the viewport meta disables pinch-zoom app-wide.

## Batch 55 — The app takes zoom away from the people who need it
**Commits:** f92ba17 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 660 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **If iOS Safari starts zooming a focused field, do not put `user-scalable=no` back.**
  The cause is an input under 16px; fix the input. `src/test/viewport.test.ts` asserts
  both halves so the attribute cannot return quietly.
- That test's element scanner tracks brace depth deliberately. An earlier draft used
  `[^>]*` to grab attributes, which stops at the `>` inside `onChange={(e) => ...}` — so
  it never reached `className` and the whole file passed vacuously. It was only caught by
  reverting a known-bad input and finding the test still green. Any similar JSX-scanning
  test needs the same care.
- `min-h-6` on `FormLine`'s disclosure is WCAG 2.2 SC 2.5.8 (24x24), not decoration.
  Measured 70x22 before, 70x24 after.
- The five "Find a league" links are 82x18 and **conformant** — SC 2.5.8 exempts a target
  inline in a sentence. Do not "fix" them.
- Pick screen now reports **zero** axe violations at 390px in both themes.

**Next:** Batch 56 — changing a PIN revokes nothing and the reset flow notifies nobody.

## Batch 56 — Two halves of account recovery, neither of which works
**Commits:** 5f88f41 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 667 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **Changing a PIN now logs the member out everywhere, including the device they used.**
  That is deliberate, not a bug: the endpoint authenticates with an *access* token so the
  API cannot tell which refresh token is the caller's, and `device_hint` would spare an
  attacker who copied the User-Agent. `lib/api.ts` already bounces a failed refresh to
  /login, so the member is simply asked for the new PIN.
- The 24-hour access token still cannot be recalled — it is stateless. A revoked session
  keeps working until that token expires, then dies at refresh. Shortening `ACCESS_TTL`
  is a separate decision nobody has taken.
- `pin/reset-request` writes `ActionType.player_pin_reset` with `changes.stage =
  "requested"` rather than a new enum value. `ALTER TYPE ... ADD VALUE` is irreversible
  and production has no restore point, which is not a trade worth making for a label.
- **`audit_log` has no reader anywhere** — no query in `src/`, no frontend surface. That
  is why the reset request also pushes. If an admin surface is ever built, that table is
  where the history already is.
- **Open question for the owner:** `_notify_site_admins` looks for `UserRole.admin`
  profiles. The e2e seed creates none, so nothing was pushed in local verification. Worth
  confirming production actually has a site admin with a live push subscription, or the
  audit row is again the only trace.
- A **`/ship-prod` is owed** from this batch — it is the first backend change since the
  review and Railway does not move on a push to `main`.

**Next:** Batch 57 — three things wrong in the file that takes the pick.

## Batch 57 — Three things wrong in the file that takes the pick
**Commits:** 43183ad · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 674 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **The provider budget is fully committed.** Measured: peak browsing hour 28, ad-hoc
  rounds 60/hour, leaving ~12 of the 100/hour plan. Any new provider call in the request
  path has nowhere to come from — check `test_request_budget.py` before adding one.
- `PICK_SUBMIT_LIMIT` bounds **one member**, not the league. Fifteen members at 10/hour is
  150 against a 100/hour plan. `test_the_pick_path_is_not_bounded_in_total_and_this_is_known`
  asserts that gap still exists; if it ever fails, the gap was closed and the test should be
  replaced rather than deleted.
- The lock re-check reads the **clock**, not the row: `pick_refusal` gets the ORM object
  already loaded in the request's session, so a `locks_at_utc` changed by another session
  is invisible to it. Any test of that race must move time, not the deadline.
- `ruff format` wanted two files after this batch's edits and `ruff check` did not. Format
  is the *first* CI step, so a check-only pass locally still fails the job — run both.

**Next:** Batch 58 — the rate limits that are decorative (X-Forwarded-For, token reuse,
correlation id, token pruning, weak PINs).

## Batch 58 — The rate limits that are decorative, and the ones that are not
**Commits:** 9ecaa00 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 687 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- `client_address` counts **from the right** now. `trusted_proxy_count` (default 1) is how
  many proxies in front of the app are ours. Raise it only if a CDN is put in front of
  Railway — getting it too high reads a caller-supplied hop again, which is the bug.
- **Do not prune `refresh_tokens` aggressively.** A revoked row is the only evidence
  `/auth/refresh` has that a token was *replayed* rather than merely unknown. The 7-day
  `REFRESH_TOKEN_RETENTION` is what keeps reuse detection working; shortening it re-hides
  theft.
- Reuse detection revokes **every** token for the member, because rotation leaves no
  lineage to walk. If per-family revocation is ever wanted, the rows need a family id.
- `WEAK_PINS` is deliberately ~34 entries. Two existing tests broke on it (Batch 56 had
  used `5678`), which is the list working. Growing it much further starts refusing PINs
  people picked for real reasons.
- `Cache-Control: no-store` does **not** affect the PWA's offline cache — the Cache Storage
  API ignores HTTP cache headers, and Workbox's `CacheableResponsePlugin` filters on status.
- Two tests asserted the old, wrong behaviour and were rewritten:
  `test_client_address_prefers_first_forwarded_for_ip` and `test_correlation_id_passthrough`.
- A **`/ship-prod` is still owed** — Batches 56, 57 and 58 are all backend.

**Next:** Batch 59 — dependency advisories (starlette/FastAPI, cryptography, react-router).

## Batch 59 — Twenty-nine advisories, three packages, one real upgrade *(part)*
**Commits:** 576d4d5 · verified: ruff 0.5.4 · mypy 1.11.0 · pytest 692 (clean schema, 0 skips) · lint · tsc · build · vitest 538

### Key facts for future sessions
- **cryptography does see untrusted input**, contrary to what `requirements.in` claimed
  until now: `push/subscribe` stores the browser's `keys` verbatim and `webpush()` parses
  `p256dh` as an EC public key. Any future reasoning about that pin has to start there.
- The bound is now `==48.0.1`, with a **ceiling** as well as a floor, and
  `tests/test_dependency_floors.py` asserts both with the reachability argument attached.
  49.0.0 publishes no macOS wheel at all — that is what `--only-binary=cryptography` in
  `ci-local.sh` is now waiting to catch.
- "No Intel wheel above 46.0.3" was not quite right: there is no *x86_64-tagged* wheel, but
  `universal2` carries an x86_64 slice and installs on Intel. Verified with the exact
  `--only-binary` invocation `ci-local.sh` uses.
- **The FastAPI upgrade was actually built and run, not estimated.** `fastapi 0.141.1 /
  starlette 1.6.0 / pydantic 2.13.4` gives 684/687. Do not repeat that exploration —
  Batch 61's row records the three failures and what each one costs.
- Of those three, the one that matters most is `test_wire_datetimes.py`: its model walk
  returns an **empty set** under pydantic 2.13, so the guard on Batch 43's 14:30-shown-as-13:30
  fix would go quiet rather than fail loudly. Rewrite it *and* prove it still catches the bug.
- react-router's open-redirect advisory is **not reachable**: the only data-built navigate
  targets are `/leagues/${league_slug}` and `_slugify` reduces a slug to `[a-z0-9-]`.

**Next:** Batch 60 — make the gate run what it claims to run.

## Batch 60 — Make the gate run what it claims to run
**Commits:** bc18bb1 · verified: `scripts/ci-local.sh` PASS (10 checks, 0 skips)

### Key facts for future sessions
- **`scripts/ci-local.sh` is the gate.** One command: pinned venv, clean `pgserver`,
  `alembic upgrade head`, full pytest, deployment-config assertions, frontend
  lint/typecheck/test/build. `SKIP_PROD_BUNDLE=1` drops only the Playwright smoke.
  It already existed before this batch — the batch was specified to build it.
- Its header comment already documented the FastAPI 403→401 `HTTPBearer` change that
  Batch 59's upgrade trial rediscovered, and records that it once cost nine days of
  local-pass/CI-fail. Read that file before touching the pins.
- Hand-run pytest **must start from a clean schema every time**. The pick-flow test and
  the e2e seeder both commit, so a reused cluster fails `test_seeds` on the second run.
  That cost time twice during this review before it was written down.
- **Still open (OPS-04):** the service worker gives `/api/v1/` GETs a 3-second
  `networkTimeoutSeconds`. Tight for mobile data against a service that can cold start;
  raising it trades a slower first paint for fewer outright failures. Left out of this
  batch because its scope boundary was tooling and docs only.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 62 — The half of the palette Batch 54 could not fix
**Commits:** 69c2f08 · verified: `scripts/ci-local.sh` PASS (10 checks) · axe 0 violations both themes

### Key facts for future sessions
- **`text-*` and `bg-*` no longer resolve to the same value for brand names.**
  `tailwind.config.ts` has a `textColor` scale pointing at `--*-ink`; `colors` still backs
  every fill, border and ring. Adding a new brand colour means adding *both*.
- **Never darken a fill to fix contrast.** That is the wrong half — it makes the near-black
  `--on-primary` sitting on it worse. `contrast.test.ts` asserts the fill pairing precisely
  so that move fails loudly.
- **A `tailwind.config.ts` change needs the dev server restarted.** HMR picks up `index.css`
  but not the config, so the old utilities keep being served — which looked exactly like a
  broken token for a while.
- `--text-inverse` pairs with an inverted *ground*, not with a brand fill. Text on a fill is
  `--on-primary`. An assertion confusing the two fails on a pairing the app never renders.
- axe measured immediately after a theme toggle catches `transition-colors` mid-flight and
  reports the outgoing palette's value. Let it settle before trusting a reading.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 63 — The product had no way to make an account
**Commits:** fbb0403 · verified: `scripts/ci-local.sh` PASS (11 checks) · browser end-to-end on the desktop and mobile paths

### Key facts for future sessions
- **A display name is now claimable by anyone, permanently.** It is globally unique, it is
  the login identifier, and `Profile` has no email or phone — so there is no way to prove
  who owns one and the only recovery is `pin/reset-request` paging a site admin. The
  uniqueness check deliberately **includes soft-deleted rows**: `deleted_at` must not
  release a departed member's identity to a stranger.
- **`PUBLIC_SIGNUP_ENABLED=false` closes the API but not the UI.** The "Create account"
  links on `/login`, `/join/:token` and `/welcome` stay visible and lead to a form that
  403s. Gating them needs `GET /api/v1/config` made unauthenticated, which reverses the
  decision written into `routers/config.py` ("nothing unauthenticated needs it, and it says
  a little about how the deployment is configured"). Left as an owner decision.
- **slowapi answers 429 with `{ error: ... }`, not `{ detail: ... }`.** Any client that
  reads `detail` silently turns a rate limit into a generic failure and invites a retry
  against a limit already spent. Fixed in `AuthContext.establishSession`; other `fetch`
  sites have not been audited for it.
- **`/register` is unreachable on an uninstalled mobile browser, by design.**
  `InstallPromptController` renders `BrowserOnboarding` full-screen over every route not in
  `SELF_MANAGED` (`/join/`, `/welcome`), so mobile installs first and registers inside the
  PWA. The onboarding copy now says exactly that. `next` does not survive the install.
- **A `public_open` league is now reachable by anyone with an account**, where before it
  was limited to members the operator provisioned. `the-coupon` is `private` and
  unaffected; the `test` league is `public_open`, and the 2026-08-20 decision to leave it
  in place was taken while account creation was closed.
- **This is the first batch whose Vercel/Railway gap is user-visible.** Pushing `main`
  deploys a "Create account" button that has no endpoint behind it until `/ship-prod` runs,
  and `/ship-prod` requires the commit to already be on `origin/main` — so the window
  cannot be avoided, only kept short. Batches 38 and 43 were built to tolerate that gap;
  this one cannot.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Fix — three member-reported bugs (claimed games, join, competition order)
**Commits:** 73245a7 · verified: `scripts/ci-local.sh` PASS (11 checks), 745 backend tests against real PostgreSQL

Not a `BUILD_PLAN` batch — reported from use, closed on the hotfix path like `b9e78fa`.

### Key facts for future sessions
- **Every production league is on `pick_scope = 'selection'`**, so "someone took Everton,
  I could still take the draw" was the configured rule, not a defect. The owner wants
  `fixture`. Switching is a **League Settings / PATCH** action, never raw SQL:
  `_apply_pick_scope_change` refuses the switch with `PICK_SCOPE_CONFLICT` when two members
  already share a pending game, and restamps pending rows — `picks.pick_scope` is what the
  partial unique index reads, so rows left on the old value are exempt from the new rule.
- **`zoe` cannot switch yet.** Zoe Waddell (HOME) and Craig (DRAW) both hold Everton v
  Crystal Palace on the 2026-08-22 round. That clash has to clear first. The other four
  leagues would take the switch today.
- **Ship the API before flipping the scope.** Production ran a slate that marked *every*
  selection on a game the caller holds as `mine`, which greys out the whole game client-side
  and locks the one member allowed to move between its markets out of doing so. Flipping
  first would have shipped that.
- **`mine` and "who blocks this" are two different questions.** `_selection_options` blocks
  only on a holder who is somebody *else* (matching `_claim_conflict`'s `holders - {player_id}`),
  and the exact holder of a selection outranks the fixture-level blocker. Reading the
  fixture blocker first hands the caller's own pick to the other member — which a league
  switched from `selection` to `fixture` will really have, since old rows survive.
- **A cache the UI gates on must be dropped, not invalidated.** `['leagues', 'mine']` is held
  for 60s and every coupon surface gates its query on `hasLeagues`; `invalidateQueries` keeps
  serving the stale list during the refetch, which is the "You're not in a league yet" empty
  state again. `dropStaleMemberships` uses `removeQueries` so the screen shows a skeleton.
- **Batch 64 (110f85b) never got a session-log entry or a STATUS mention.** Its close-out is
  incomplete; left alone here rather than reconstructed from the diff.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 64 — The card offered five games that were not being played
**Commits:** 5d2a964, merge 110f85b · verified: `scripts/ci-local.sh` PASS, 16 new backend
test cases, and a run against the live production card — 137 fixtures in, 8 marked off,
all 8 already removed by hand, nothing condemned that was on

Closed out retroactively: the code merged and reached production on 2026-08-22 before its
paperwork existed, which the preceding hotfix entry flagged.

### Key facts for future sessions
- **A postponement is invisible on date alone.** FotMob keeps a postponed match's
  *original* `utcTime`, so `status.cancelled` is the only tell. A date-only cross-check was
  written first, passed review, and cleared Rangers v St Mirren and St Johnstone v Celtic —
  the two most visible games on the card. The rule is `cancelled` **OR** date mismatch;
  either half alone is a silent failure that looks like success.
- **Bookmaker prices are not evidence a fixture is on.** Bet365 priced every postponed
  Premiership game. A price says *upcoming*, never *upcoming today*. Arguing from live odds
  cost a whole diagnostic pass.
- **`verify_slate` deliberately fails open, and the alias layer is why it can.**
  `team_matching`'s normaliser rates "RC Warwick" against "Racing Club Warwick" at 0.83
  where the naive token scorer written first gave 0.33 and would have deleted a real game.
  Both ends must clear `PAIR_THRESHOLD` 0.80 — that pair requirement is what makes the
  subset trap safe, since "Rangers" scores 0.95 against "Queens Park Rangers".
- **Hand-removing a fixture does not stick, and this is still true after Batch 64 for
  anything FotMob cannot see.** `sync_slate` only ever *adds* links and nothing persists the
  judgement — there is no status column on `fixtures`. Proved by running the real
  `refresh-slate` against production and rolling back: 10 of 12 hand-removed fixtures
  re-linked to both leagues, 90 minutes before the lock. FotMob carries neither NI
  Championship 1 nor the English non-league tiers, so a removal there is provisional until
  the round locks.
- **A production dry run spends the scheduler's own odds-api.io budget.** Anything routed
  through `fetch_slate` is a real metered call, not a probe. Two dry runs exhausted the
  100/hour, and the 13:00 `refresh-slate` then almost certainly hit the same 429 and
  no-opped — invisible except as `log.exception("slate refresh failed")`. Rebuild a `Slate`
  from `fixtures` rows instead; FotMob is unmetered and free to hit.
- **This batch never ran its own `/ship-prod` — it reached production as a passenger on
  `82a7a12`.** Confirmed on the running container, not inferred from git, because
  `railway up` uploads the *working directory* rather than the commit. That same property
  blocked the deploy earlier: a shared dirty worktree carrying another session's in-flight
  work would have shipped it, which is exactly what the clean-worktree preflight is for.

**Next:** Batch 61 — the FastAPI/starlette upgrade and the two decisions inside it.

## Batch 65 — The week ends at the lock, and it should end at the results
**Commits:** a2a6dca (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 753 backend tests against real PostgreSQL), 9 new backend test cases

Two independent causes of one member report, fixed together because either alone leaves
the complaint half-standing.

### Key facts for future sessions
- **A correlated subquery is legal inside a PostgreSQL window `ORDER BY`.** That is what
  keeps `current_round_order` a self-contained bag of ORDER BY clauses: the in-play bound
  needs the owning league's window, and a *join* would have to be added to both call sites
  — where a future caller forgetting it produces a silent cross product rather than an
  error. Probed against pgserver before committing to the shape.
- **`span_days` needs `((a - b) % 7 + 7) % 7` in SQL.** PostgreSQL's `%` truncates
  toward zero, so a Friday-to-Monday window (`0 - 4`) computes as *minus four days* where
  Python's `%` gives three. The Python `SlateWindow.span_days` is correct; a naive
  transliteration into SQL is not.
- **The in-play bound is measured from the window's *close*, not the lock.** Measuring
  from the lock is right only for a league whose window is a single point — the default
  Saturday 15:00 — and drops a long-weekend league out of its own round while Monday's
  games are being played. Derived as `lock_offset + span_days + (end_minute -
  start_minute)` minutes after `locks_at_utc`, which needs no timezone conversion in SQL
  and is at most an hour out across a DST change.
- **Decision — the bound is 48 hours (`IN_PLAY_GRACE_MINUTES`), from the settlement
  cadence.** Settlement sweeps at 18:00, 20:00 and 22:00 daily, so two days is six
  consecutive sweeps: a round unresolved by then is stuck, not in play. Stated in
  `test_a_round_that_never_settles_stops_pinning_the_league` on both sides of the line.
- **Decision — `status` is not re-derived when a window edit restamps the instants.**
  Only `picks_open_at_utc` and `locks_at_utc` move. Flipping a round back from `open` to
  `scheduled` would tell members a round they may already hold a pick on has not opened,
  and it buys nothing: `pick_refusal` and `accepting_picks` both read the instant, and
  `open_due_gameweeks` re-labels on its next run.
- **Decision — the restamp is logged, not written into the audit row's `changes`.** That
  payload is a `{field: {from, to}}` map and a count does not fit it; Batch 69's console
  will render it. `league.claim_periods_restamped` carries the league and the round count.
- **Batch 27's "neither instant is ever re-derived" is now half-true and the docs said it
  in four places.** `models/gameweek.py`, `sync_slate`, `populate_cadence_rounds` and
  `test_round_population.py`'s header all asserted it. The surviving half is the
  load-bearing one: a *locked* round keeps the deadline it was claimed against.
- **Two existing tests asserted the old behaviour as their subject and were rewritten, not
  patched.** `test_refresh_rounds_rebuilds_a_moved_window_without_moving_the_announced_
  instants` held that a PATCH may not move an unlocked round's instants — now exactly
  backwards — and `test_slate_and_coupon_read_a_named_gameweek` defaulted to next week's
  round while last week's was still being played. Both now assert the new rule at the HTTP
  layer, which is where the member saw the defect.

**Next:** Batch 66 — a member who forgets their PIN has no way back in.

## Batch 66 — A member who forgets their PIN has no way back in
**Commits:** e765e75 (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 769 backend tests against real PostgreSQL, 668 frontend), 16 new backend and
16 new frontend test cases, and the prod-bundle Playwright smoke extended to both new
routes

### Key facts for future sessions
- **This batch adds Alembic revision 016 — the only schema change in the 65→72 run.**
  `profiles.pin_hash` drops `NOT NULL`. No data moves and the constraint is only relaxed,
  so it is safe against a live database; the *downgrade* fails while any member is
  mid-reset, which is correct rather than a defect. Production has no restore point
  (owner's 2026-07-30 deferral), so the `/ship-prod` that carries this wants a written
  forward recovery plan.
- **The row's decision required the migration.** "Clears the credential and forces
  set-on-next-login" is only expressible if the column admits NULL. The alternative that
  avoids a migration — a sentinel value in `pin_hash` — puts an in-band signal in a
  credential column, which is how a "is this a hash or a marker?" bug gets written later.
  `Mapped[str | None]` makes mypy walk every read path instead.
- **A cleared PIN is claimable by whoever names the account, and that is inherent.** No
  secret passes through the admin, so nothing proves the caller is the member, and display
  names are on every leaderboard. Bounded rather than accepted: `PIN_RESET_CLAIM_WINDOW` is
  24 hours, read from the `player_pin_reset` audit row the reset already writes. **No new
  column** — `pin_hash IS NULL` already carries the state, and setting a PIN closes the
  window by making its own condition false, so it is single-use without a "used" flag.
- **The audit row is load-bearing, not decoration.** `/auth/pin/set` reads it for the
  window, so a reset that is not recorded is a reset that cannot be used. It has to be the
  *newest* row for that member: `pin/reset-request` writes the same `ActionType` at stage
  `requested`, so a member asking again must not re-open a window an admin did not.
- **A pre-existing league-admin PIN reset was found, and it was the defect the row
  describes.** `POST /leagues/{slug}/members/{id}/reset-pin` minted a temporary four-digit
  PIN, returned it for the admin to read out, skipped `is_weak_pin`, and **revoked
  nothing** — sessions opened under the old PIN kept renewing for thirty days past it.
  Nothing in `apps/web` called it and no test asserted `temp_pin`, so it was changeable
  without a deploy-window risk. It now shares `services/credentials.clear_pin`.
- **Decision — `temp_pin` stays in that response, always null, rather than being
  removed.** Vercel deploys the web app on merge while the API waits for `/ship-prod`, so
  a removed field breaks any client still reading it in the gap — the trap Batches 38, 41
  and 48 each recorded. It can go once both halves have shipped.
- **Decision — no new `ActionType` values.** `ALTER TYPE ... ADD VALUE` cannot be undone.
  The unlock endpoint therefore writes **no audit row at all** (structlog only) — it takes
  nothing away and grants no access, so that is the proportionate trade — and the site
  delete reuses `member_removed` with `target_table="profiles"` and `{"scope": "site"}`.
- **`from __future__ import annotations` breaks FastAPI dependency aliases.** Ten test
  modules failed at collection with `PydanticUndefinedAnnotation: name 'AdminUser' is not
  defined` until it was removed from `routers/admin.py`. No other router in the repo has
  it, which is now known to be the reason rather than a style choice.
- **The non-admin gate is asserted by walking `admin_router.routes`**, not by listing
  endpoints. A hand-written list only covers the routes somebody remembered to add to it —
  the same class of omission that left the league-admin reset unrevoked for ten batches.

**Next:** Batch 67 — what a round looks like once it has been played.

## Batch 67 — What a round looks like once it has been played
**Commits:** 7e28702 (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 783 backend tests against real PostgreSQL, 675 frontend), 11 new backend
service tests, 3 new HTTP-level tests, 7 new frontend test cases

### Key facts for future sessions
- **Decision — the fixture-to-match link is resolved per read, not persisted.** The row
  left it open. Persisting adds a column *and* a backfill against a database with no
  restore point, and Batch 66 had already spent this run's one migration; resolving costs
  one extra query on a screen read a handful of times a week per league. The deciding
  argument was not cost: a stored link goes stale when an alias is **corrected**, and the
  alias layer is the part most likely to need correcting. If Batch 72 makes this hot, the
  shape to reach for is a cache in front of it, never a column.
- **`PAIR_THRESHOLD` and `pair_score` moved from `slate_verification` into
  `team_matching`.** Batch 64 put them where the first caller was. They are a judgement
  about club names, so they belong with the rest of the name matching; `pair_score` now
  takes four raw strings and normalises them itself, so a caller holding provider text and
  one holding a stored `normalised_name` cannot disagree about what was compared.
- **`CANDIDATE_WINDOW` is ±3 days, and the *order* of the two rules is what matters.**
  Name first, then date — never name score alone. A home-and-away pair inside one season
  matches both ends equally well, so "best score wins" would pick arbitrarily between two
  correct-looking answers. Batch 64 learned the same lesson from the other side, where
  choosing by name compared the card against a game six months out.
- **The ambiguity guard fired for real, in the test suite, on the first run.** Three
  finished "Arsenal v Chelsea" rows on one day, because `test_picks_flow.py` commits and
  the fixture pool is shared by `provider_event_id`, so every test in that module works
  against the *same* fixture row. `_record_played_match` now clears the competition's
  window before seeding. Worth knowing twice over: the guard works, and that module's
  non-hermetic seeding accumulates across tests in ways that look like product bugs.
- **UK-date comparison, not UTC-date.** A 23:30 UTC Friday kick-off is Saturday in UTC and
  Friday in London, and the two records store the same instant. Comparing raw dates would
  separate matches a member thinks of as the same night.
- **Only `finished` matches produce a scoreline, and only settled rounds ask for one.**
  Two gates, deliberately: an in-play match carries a partial score, and a partial score
  printed beside a settled pick would say the round is still moving. Batch 72 reads the
  in-play side and must not reuse this path unchanged.
- **All three new `CouponLeg` fields are optional with a default** — `points_awarded`,
  `home_goals`, `away_goals` — and there is a frontend test asserting the view still reads
  correctly when the deployed API sends none of them, which is exactly the Vercel-ahead-of-
  Railway window.

**Next:** Batch 69 — the operational half of the admin console. (Batch 68 is deliberately
out of the unattended run: it cannot start without an odds figure only the owner can
evidence.)

## Batch 69 — The operational half of the admin console
**Commits:** f6cd9b3 (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 806 backend tests against real PostgreSQL, 687 frontend), 20 new backend test
cases, 3 new budget assertions in `test_request_budget.py`, 12 new frontend test cases

### Key facts for future sessions
- **The durable fixture status is NOT in this batch, and the row's own instruction is
  why.** `fixtures` has no status column, so an admin removal that survives the next
  `refresh-slate` needs a migration; the row says to decide before starting and split it
  out if it does. It does. FotMob still carries neither NI Championship 1 nor the English
  non-league tiers, so a hand-removal there is still undone by the next refresh — the gap
  Batch 64 recorded is unchanged and now needs a batch of its own.
- **The manual trigger shares the ad-hoc slate bucket rather than taking one of its own.**
  `PROVIDER_SLATE_FETCH_LIMIT` / `PROVIDER_SLATE_FETCH_SCOPE`, imported from
  `routers/leagues.py`, and there is a test asserting the two are the same object. Two
  `2/hour` limits against a plan with room for two is `4/hour` — the arithmetic error
  Batch 57 found on the pick path.
- **The bucket is denominated in slate walks, not presses.** One ad-hoc fetch is one walk
  of the thirty UK competitions, so `ManualJob.budget_units` is `ceil(provider_requests /
  30)` and discovery — which walks the whole `slate_horizon_weeks` horizon — is charged
  twice. Charging it once would let an admin spend sixty requests against a bucket sized
  for thirty.
- **`backup` and `football-backfill` are deliberately not offered as buttons.** Backup
  writes a file to the container's disk that an admin pressing from a phone cannot reach;
  the backfill is a one-off whole-season pull. Both stay in `run_scheduled.JOBS` for the
  cron entry point, so excluding them from the screen is a list, not a removal.
- **Manual settlement takes a scoreline, not market verdicts.** Both markets follow from
  a score, and asking an admin to say separately whether both teams scored is asking for
  arithmetic the code can do and for a mistake nothing would catch. The score becomes an
  `EventSettlement` and goes into `settle_gameweek` **unchanged**, so hand-entered and
  provider-supplied results write identical rows — asserted field by field on two
  identical rounds settled each way.
- **A settled round refuses a second settlement (409).** This corrects a round that is
  stuck, not one that is finished; rewriting a settled week would move points members have
  already seen. A genuine correction means editing the pick, which is a different act.
- **A path parameter named `key` was shadowed by a local `key = per_user_key(request)`,**
  and the endpoint returned the rate-limit key as the job name. Caught by an exact-equality
  assertion on the response body, which a looser `status_code == 200` would have missed.
- **Run mypy the way `ci-local.sh` runs it.** `mypy /abs/path/src` with `PYTHONPATH` set
  passed while `mypy src` from `apps/api` failed with two `comparison-overlap` errors: the
  409 guard narrows `gameweek.status` to "not settled", and `settle_gameweek` is precisely
  the call that can have changed it since. Re-read through `GameweekStatus(...)` after the
  call rather than trusting the narrowed attribute.
- **`enabled` and `running` are separate fields on the scheduler status on purpose.** The
  configured intent and the fact come apart in the one case worth knowing about — a
  container whose APScheduler never started — and the runbook's answer to that is the
  external cron, which the manual triggers are now a third route to.

**Next:** Batch 70 — what kind of picks people are actually making.

## Batch 70 — What kind of picks are people actually making
**Commits:** 6b58d9e (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 814 backend tests against real PostgreSQL, 695 frontend), 7 new backend
service tests, 1 new HTTP-level agreement test, 8 new frontend test cases

### Key facts for future sessions
- **Decision — void picks count in `picks_played` and not in the odds figures.** The row
  called this the decision to record. A postponed fixture is a round the member took part
  in, so it stays in the played count; it is also a bet that never ran, so its price is
  not folded into a cumulative total. `picks_priced` (won + lost) is the new denominator
  and is on the wire, so the difference is visible in the data rather than only in prose.
- **"Say so in the UI" is a component, not a comment.** `VoidDenominatorNote` renders
  wherever the figures render and renders *nothing* when the two denominators agree —
  printing it always would train readers to ignore it by the time it mattered.
- **`LONGSHOT_ODDS` is 3.00 and travels on every row as `longshot_odds`.** Chosen against
  the scoring rule rather than by taste: a winner scores `round(odds × 10)`, so one hit at
  3.00 outscores two at evens, and 3.00 sits clear of the 1.50-2.50 band most match-odds
  favourites occupy. Carried per row so the screen labels the split from the value it was
  computed with — the same reason `odds_degraded` travels with the odds.
- **`round(2.675, 2)` is `2.67`, not `2.68`.** 10.70 / 4 is not exactly representable as a
  float. Left as it lands rather than nudged, because the same rounding runs on every
  surface and they therefore agree with each other; the test says so in a comment so it is
  not "fixed" later.
- **The profile's own win-rate computation was deleted, not kept alongside.** It divided
  the same two numbers the aggregate already had, which is precisely how a profile and a
  leaderboard end up a rounding step apart. There is now one computation, in `Standing`.
- **Cumulative odds is a *sum*, not a product.** An accumulator's product over a season is
  a number nobody can read. The cross-league summary sums across leagues and divides by
  the summed `picks_priced` rather than averaging three per-league means, which would
  weight a one-pick league like a full season.
- **`test_cross_league_summary_shows_an_unpicked_round_and_no_leagues` asserts the summary
  as an exact dict.** That is a feature: adding a field to that response fails there
  immediately, which is the same surface the deployed web app meets before `/ship-prod`.
  Any future field has to be added to that literal deliberately.
- **Longest streak is deliberately absent.** It needs ordered history rather than an
  aggregate — a second query on a path that costs one — and the row ruled it out.

**Next:** Batch 71 — Football Stats opens expanded and shows part of the results.

## Batch 71 — Football Stats opens expanded and shows part of the results
**Commits:** bfeb0bf (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 818 backend tests against real PostgreSQL, 695 frontend), 3 new backend
service tests, 1 new HTTP-level test, and a read-only production measurement before and
after

### Key facts for future sessions
- **The measurement, because "looks fuller" is not a verification.** Read-only against
  production on 2026-08-23, via the `railway ssh` form in
  `docs/runbooks/launch-readiness.md`:
  - the whole table: **567 finished matches across 18 competitions**, every one inside the
    30-day lookback — so **ingestion is healthy** and this was *not* Batch 45's failure
    mode, which is the thing the row insisted be checked rather than assumed;
  - Saturday 2026-08-22: **145 matches across 17 competitions**;
  - what the shipped `limit=20` returned: **20 rows covering 6 of those 17**;
  - what the new 3-day window returns on the same data: **150 rows, all 17 competitions,
    3 days** — inside the 400-row backstop.
- **A flat row count was the wrong shape, not just the wrong number.** The screen groups
  by day and then by competition, so the unit of the answer has to be the day; raising 20
  to 200 would have moved the cliff rather than removed it. `football_recent_results_limit`
  is gone; `football_results_days` (3) and `football_results_max_rows` (400) replace it.
  Neither was ever set in any deployment config, so the rename ships as a code default.
- **"Days that have results", not calendar days.** Production's distribution runs from one
  match a day to 145; counting calendar days would empty the screen every midweek.
- **A naive-UTC timestamp needs `AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/London'`.** One
  conversion alone reads the naive value *as* London time — an hour wrong in summer, and
  it puts a 23:30 Friday kick-off on the wrong day. Same rule as `match_link._uk_date`.
- **The comment beside the old setting was itself the misreading.** It said "how many
  results a competition shows on the football-data screen"; it was a global cap across
  every pooled competition at once. Worth remembering that a wrong comment beside a right
  constant is how a defect survives a review.
- **Collapsing every table cost six other tests their premise.** They read rows and form
  from the Premier League card without expanding it, because it used to open by default.
  They now call an `openTable()` helper, which is the honest shape: none of them was
  asserting what the screen shows on arrival.

**Next:** Batch 72 — live scores while the round is being played.

## Batch 72 — Live scores while the round is being played
**Commits:** f05aaaa (ff-merged to local main) · verified: `scripts/ci-local.sh` PASS
(11 checks, 827 backend tests against real PostgreSQL, 700 frontend), 9 new backend tests,
5 new frontend test cases

### Key facts for future sessions
- **The FotMob payload memo is per client and the client is process-wide.** A live read
  through it returns whatever the first caller of the day saw — a poll every ten minutes
  reporting half-time until the container restarts. `_league(..., refresh=True)` replaces
  the memo rather than bypassing it, so the fresher payload is what everything else sees
  and the request is not paid for twice. This is the single easiest way to have shipped
  this batch broken and had every test pass.
- **`Match.finished` was already the right gate, and nothing needed to change to respect
  it.** `sync_results` writes `finished = result.finished and home_goals is not None`, so
  an in-play `MatchResult` stores its running score and stays out of the results screen,
  the form line and Batch 67's settled scorelines — all three filter on `finished`. The
  model's own docstring predicted this use.
- **`fetch_live_scores` is non-abstract on the port with a `[]` default**, the pattern
  `fetch_fixture_states` set for the same reason: only FotMob can answer, and a provider
  that cannot must cost nothing beyond the scores it does not supply. api-football and the
  fake needed no change at all.
- **The poll is bounded by Batch 65's `in_play`, and that does a second job here.** It
  stops a round the provider never settles being polled forever — Batch 64's phantom
  Premiership round would otherwise have kept a competition fetched every ten minutes
  until May. `is_in_play` (single-row) is a *query*, not a Python check, because the grace
  is measured from the league's window and that lives on a row the gameweek does not carry.
- **A kicked-off match with no published score is skipped, not stored as 0-0.** Nil-nil is
  a real scoreline and "we do not know" is not.
- **Four live-score tests passed alone and failed in the suite.** The poll is deliberately
  global — every league's in-play round — and other modules in the suite *commit*, so
  their rounds were in play too. The tests now scope every assertion to the competition
  slug they created, and the `_Live` fake answers for one slug rather than for whatever it
  is asked about. Worth remembering as a class: "assert nothing happened" is not a safe
  assertion against a shared committed database.
- **`Badge` renders a block, so it cannot go inside a `<p>`.** Caught by React's
  `validateDOMNesting` warning in a test that was otherwise passing; the browser silently
  rewrites the markup.
- **`score_is_final` defaults to `true` on the wire and in the client.** Absent has always
  meant final, so the deployed web app reads a pre-Batch-72 API exactly as it always did.

**Next:** Batch 68 (needs an odds figure only the owner can evidence) and Batch 61 (the
FastAPI/starlette upgrade), both deliberately outside the unattended run.

## Batch 68 — Two rounds that were played before the app was watching
**Commits:** 18dfb9f (ff-merged, pushed) · shipped to production as Railway
`5922cf17-1767-4ab8-b225-9c0d2fd6b44f` · **backfill applied to production 2026-08-24
21:27 UTC** · verified: `scripts/ci-local.sh` PASS (11 checks, 846 backend tests), 19 new
backend test cases, a production dry run, and a 24-leg hand tally

The owner supplied both bet365 slips and both coupons on 2026-08-24, which unblocked the
batch. 26 picks written across three rounds; the league's 12 members all now show three
rounds played.

### Key facts for future sessions
- **A betting slip states its own return, and that is the check worth writing.** The
  8 August slip is £3.50 to return £1,660.24; the twelve fractions multiply to 474.28, so
  474.28 × 3.50 = £1,659.99 — 0.015%, bet365's own rounding. A single mis-converted
  fraction (19/20 as 1.90) is invisible on re-reading and moves a member's points by a
  whole unit. A second test asserts each stored decimal is its own fraction rounded to 2dp,
  because the product alone survives two errors that cancel.
- **Do the product check on the fractions, not on the stored decimals.** The 2dp values
  drift ~1.1% high over twelve legs (4/6 → 1.67 three times), which is `Numeric(6, 2)`
  doing its job. My first version compared the decimals and failed at a tolerance tight
  enough to be worth having.
- **Nothing invents an outcome.** Picks were written `pending` with no points and settled
  by `settle_gameweek` against the scorelines already in `matches`. So the coupons say what
  was picked and FotMob says what happened, and `points_awarded` is *computed*. Verified
  in production: 36 settled picks, **0 mismatches** against `round(odds × 10)`.
- **The rehearsal is the thing that made this safe.** Dumping production's candidate
  matches and running the real `pair_score`/`PAIR_THRESHOLD` locally resolved 25 of 26
  before anything was written — and found **every FotMob scoreline agreeing with the
  settled 15 August slip's own ✓/✗ marks**. Two independent sources, no disagreement.
- **A naive SQL preflight lied.** Joining `teams.name = fixtures.home` reported 20 failures;
  the two providers spell clubs differently ("Everton" vs "Everton FC"), which is the entire
  reason Batch 67's join is similarity-based. If a check contradicts a shipped matcher,
  suspect the check.
- **Scotland League Cup Group C is carried by nothing.** Aberdeen v Dundee, 15 August, has
  zero finished matches in production — it joins NI Championship 1 and the English
  non-league tiers on that list. Handled by `KNOWN_SCORES`, which may only *fill* a hole:
  the run raises if an entry there would override a score the store holds. Owner confirmed
  3-0 independently of the slip, so that value has two sources — better attested than the
  two 22 August prices.
- **Decision — rounds land with `number = NULL`.** 22 August is "Gameweek 1" and members
  were told so. `next_gameweek_number` would name these 3 and 4, putting a later number on
  an earlier date; renumbering 22 August would rewrite a name in use. The column is nullable
  for exactly this and nothing keys on it.
- **Running a module against production needs the container's own environment.** The prod
  database is IPv6-only, so it has to run inside Railway — and `railway ssh` gives neither
  the venv (`/opt/venv/bin/python`) nor `LD_LIBRARY_PATH`, so greenlet fails to load
  `libstdc++.so.6`. Take it from `/proc/1/environ` without printing it; that file holds
  every secret the service has.
- **Test isolation, again.** `apply()` originally committed, which broke the rollback
  fixture for every later test; it now flushes and the CLI commits, matching the codebase
  convention. And unscoped `select(Pick)` assertions passed alone and failed in the full
  suite. Third batch running to hit that — assume the suite is non-hermetic by default.

**Next:** Batch 61 — the FastAPI/starlette upgrade, the last unchecked row.

## Batch 61 — The framework upgrade, and the two decisions inside it
**Commits:** a5966af (ff-merged, pushed) · preceded by dfc5291, an unrelated blocker fixed
on its own branch first · verified: `scripts/ci-local.sh` PASS (11 checks, **845 backend
tests against real PostgreSQL, zero skips**, whole frontend, Playwright deep-link smoke)
on `fastapi 0.141.1 / starlette 1.6.0 / pydantic 2.13.4`

### Key facts for future sessions
- **`main` was already red when this started, and it was a clock bomb.**
  `test_the_settings_edit_restamps_an_unlocked_round_and_the_refresh_leaves_it` took
  `rounds[0]` and assumed it was still claimable. `upcoming_slate_dates` includes today by
  *date* alone, never by time of day, so on the league's own weekday after its lock the
  round is born dead and `rederive_claim_periods` correctly refuses to restamp it. The test
  used a TUESDAY window, so it failed Tuesdays after 18:45 London and passed the other 167
  hours. Fixed separately in dfc5291 — **run the gate before branching**, or a red baseline
  looks like your change.
- **The datetime-wire guard had lost every route, not just its models.** The batch row
  predicted "the model walk finds nothing under pydantic 2.13"; the real cause is FastAPI's.
  0.141 stopped copying an included router's routes onto the parent and mounts a private
  `_IncludedRouter`, so `isinstance(route, APIRoute)` matched **0 of 18** where it had
  matched 73. Batch 43's guard was walking an empty set — any response model added since
  would have been unguarded. `_api_routes` now descends by structure (`.routes`, else
  `.original_router.routes`), which works on both shapes and names no private class.
- **A guard that finds nothing looks exactly like a guard with nothing to report.** That is
  why the walk now asserts floors (>50 routes, >20 models) as well as three named models:
  the named-model check alone is satisfiable while having lost almost everything.
- **The 401/403 decision is "change nothing in the client", and the reason matters.**
  `lib/api.ts` keys on 401 alone; the anonymous case moves there for free and improves.
  **Do not widen that branch to 403** — a real 403 is a signed-in member reaching an admin
  route, and refresh-then-redirect would sign them out for asking. Safe because every
  bearer-protected call is under `<ProtectedRoute />`.
- **The status-constant rename could only land with the upgrade.** Both old names still
  resolve on starlette 1.6.0 but now raise `StarletteDeprecationWarning`; on the old pins
  the new names were an `AttributeError`. `routers/auth.py` carried a comment warning
  against this exact rename and now carries its reverse.
- **19 transitives disappeared and none were used.** 0.111 bundled python-multipart,
  email-validator, jinja2, orjson, ujson, fastapi-cli, typer and rich; 0.141 puts them
  behind a `[standard]` extra. `routers/auth.py` already documents that avatar upload reads
  the raw body *specifically* so python-multipart never became a dependency — that decision
  is what made this drop free.
- **`/ship-prod` is owed and this one actually matters.** Every previous drift this session
  was docs and tests. This changes the API's dependency tree and its anonymous-caller status
  code, and Vercel has already shipped the web half.

**Next:** Batch 73 — the round badge that reads `status` rather than time.

## Batch 73 — A round can say "open" while it is refusing picks
**Commit:** 72b1c4a (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks, **715
frontend tests across 48 files**, plus the whole backend and the Playwright smoke)

### Key facts for future sessions
- **`lib/coupon.ts` now holds the rule.** `pickRefusal(round, now)` mirrors the API's
  `pick_refusal` case for case, **including the ordering**: the opening gate is tested
  before the deadline, so a round that has not opened answers `PICKS_NOT_OPEN` rather than
  `PICKS_LOCKED` and is still restampable. A fixture that locked before it opened is what
  proved this — the component kept the round, correctly, and the fixture was the wrong
  thing. Mirror the order, not just the outcomes.
- **`status` is a lagging label, everywhere.** `open_due_gameweeks` moves
  `scheduled -> open`; the lock job moves `open -> locked`; neither runs backwards and both
  are hourly. **Any screen that branches on `status` is wrong for up to an hour at each end
  of the claim period.** Two were found this batch; assume more when touching a surface
  that labels a round.
- **The settings page was actively lying to admins.** Its copy said a change "never
  restamps a round that already exists" — correct when Batch 40 wrote it, false from Batch
  65, and it is the sentence an admin reads *while making that change*. **When a batch
  changes a rule, grep the UI copy for the old rule.** Batch 65 did not.
- **The same screen's round list had the same bug.** `upcoming()` filtered on `status`, so
  a round past its deadline was listed as one the setting still moves, when
  `rederive_claim_periods` bounds on `locks_at_utc > now` and skips it.
- **A time-aware filter turns date-blind fixtures into a clock bomb.**
  `LeagueSettingsPage.test.tsx` carries absolute August 2026 dates. They were safe only
  because the old filter ignored dates entirely; the new one would have passed on
  2026-08-25 and failed from 2026-08-29. Pinned to a fixed `NOW` — the same failure
  `dfc5291` had just removed from the backend, nearly reintroduced on the frontend.
- **`CouponPickPage` deliberately still states the rule a third time**, through
  `useCountdown`, because it must flip live while a member watches and it gates *submission*
  rather than a label. Both sides carry a pointer to the other. **Candidate follow-up:**
  fold it onto `pickRefusal` once someone is willing to test the submit path properly.
- **`PickShapeLine` lost the longshot split** (`avg 2.67 · 0 at 3.00+`) and is now
  `avg odds selected 2.67`. The split lives on `PickShapeGrid`, and the test proving the
  label tracks the league's configured line **moved there rather than being deleted** —
  the guarantee still applies on the surface that still shows it.

**Next:** Batch 74 — renumbering 2-1 Hibs' rounds and renaming three members.

## Batch 74 — Four rounds and three members in 2-1 Hibs are called the wrong thing
**Commit:** 9cf1686 (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks), 9 new
Postgres-backed tests · **script shipped, NOT applied to production**

### Key facts for future sessions
- **The production dry run is still owed.** `python -m src.backfill_names_and_numbers
  --dry-run`, then `--apply`, then **tell the owner and members A and B their new sign-in
  names**.
  `docs/backfills/2026-08-names-and-numbers.md` carries the pre-flight checklist.
- **A Supabase MCP timeout is not a database outage, and this session proved it.** Every
  query through the MCP timed out including `select 1`; `check-deploy-drift.sh` run
  immediately afterwards had the deployed API answering with `migration 016`, which it can
  only know by querying that same database. **Discriminate this way before reporting an
  outage** — the failure was confined to the MCP's connection path (probably the pooler
  endpoint rather than the direct DSN), while members were served normally throughout.
- **Renaming a profile releases its name more completely than deleting one does.**
  `auth.py:436` reserves names case-insensitively and **deliberately includes soft-deleted
  rows**, so a departed member keeps their name — but a rename leaves no row holding the
  old one, so "Craig" and both members' old names become registrable by anyone the moment this
  applies. Counter-intuitive and worth remembering before any future rename.
- **`display_name` is the login identifier**, matched exactly at `auth.py:228` and again at
  `auth.py:695` for PIN resets. The JWT subject is the player id, so a rename signs nobody
  out — it breaks their *next* sign-in instead, which is the failure nobody connects to a
  change made days earlier.
- **`(league_id, number)` carries no unique constraint** — `uq_gameweeks_league_starts_on`
  is the only one on `gameweeks`. Two rounds can both be "Gameweek 3" and only an explicit
  read catches it, which is why `_assert_season_reads` re-queries rather than trusting the
  plan it just applied.
- **This reverses Batch 68's numbering decision, and that decision was not wrong.** It
  weighed rewriting a name members had used against a season that read out of order; the
  owner has now weighed it the other way. Both comments say so, so neither reads as an
  oversight later.

**Next:** Batch 75 — removing the nightly `pg_dump` that writes to a tmpfs no volume backs.

## Batch 75 — The nightly backup pulls the whole database across the internet and throws it away
**Commit:** d012ebf (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **Production has no backup at all, and this batch made that visible rather than causing
  it.** `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md:105` records the owner's 2026-07-30
  deferral: no managed backup, no PITR. So `backup-restore.md`'s "Supabase managed
  backups are the source of record" is **aspirational, not current**. The nightly dump was
  never a fallback — it wrote to `/tmp` on a service with no volume — but it logged
  `"scheduled backup complete"` every night, which was a false signal. **The real gap is
  still open and is not this batch's to close.**
- **Removing it is not the egress fix and must not be cited as one.** 12 MB of database
  and this job put The Coupon near 1 GB/month against a 5 GB allowance, and Supabase meters
  egress **per organisation** — so the thing that spent the quota may be a different
  project entirely. That question is unanswered.
- **The schedule went; the capability stayed.** `python -m src.run_scheduled backup` runs
  the same coroutine. `services/backup.py`, `settings.backup_dir`, `test_backup.py` and the
  `backup_failed` / `backup_downloaded` enum values are all untouched — enum values are
  irreversible to remove, for the reason `unlock_player` records.
- **Assert a removed job absent, and pair the assertion.** `daily_backup is None` in
  `test_scheduler.py` plus "the manual path still resolves to the same coroutine" in
  `test_run_scheduled.py`. **Either alone passes the wrong change**: delete the coroutine
  and the first still passes; restore the nightly `add_job` and the second still passes.
- **A comment justifying a time can outlive the thing it referenced.**
  `prune_refresh_tokens` ran at 04:30 "after the 03:00 backup so a pruned row is in last
  night's copy". The hour kept a real reason — PITR holds that property *better*, since it
  recovers a row deleted at 04:30 to any second before it — rather than being left
  pointing at a job that no longer exists.
- **Launch-phase docs were deliberately not rewritten.** `LAUNCH_PLAN.md`, `L0` and `L3`
  describe the nightly dump; they are dated records of what was true then, the same
  convention Batch 74 applied to `invites.display_name_hint`.

**Next:** Batch 76 — notification triggers, and making the per-league mute actually work.

## Batch 76 — Notifications for the three moments that matter
**Commit:** dc4fe16 (ff-merged) · verified: `scripts/ci-local.sh` PASS (11 checks), 11 new
Postgres-backed tests

### Key facts for future sessions
- **`send_notification` now takes `league_id`, and a trigger that forgets it fails
  silently.** The message still sends; only the mute goes unconsulted. That is why each
  trigger has an explicit assertion that it passes the kwarg — the behaviour is invisible
  otherwise. **Any new league-scoped notification must pass it.**
- **The mute gate fires only on an explicit `notification_muted = True`.** A missing
  membership does not suppress, deliberately, so Batch 76 is purely additive.
- **Testing the gate needs VAPID configured.** `send_notification` bails out at the top
  when VAPID keys are unset, so a test asserting `== 0` with them unset passes on the
  early return and proves nothing. Patch `settings.vapid_*` and
  `_send_push_sync` instead, and assert the push was not attempted.
- **`members_missing_picks` keeps its own mute filter on purpose.** Not belt-and-braces:
  `send_pick_reminders` returns who was *targeted*, so suppressing downstream instead
  would have that count claim a league was reminded when nobody was.
- **The reminder is hourly now and most runs match nothing** — that is the designed shape,
  which is why the empty case logs at debug. `gameweeks_due_a_reminder` selects
  `locks_at_utc` in `T-3h ± 30min`; an exact predicate cannot be hit by a cron.
- **Its eligibility mirrors `pick_refusal`, not `status == open`** — Batch 73's lesson, and
  it matters more here: with a 30-minute window, an hour of stale label loses the reminder
  rather than delaying it.
- **`submit_pick` builds its response before the alert block.** The block rolls back on
  failure and **a rollback expires every object in the session**, so serialising afterwards
  would lazy-load the committed row outside the transaction just discarded. Watch for this
  anywhere a post-commit side effect can roll back.
- **`moved` must be captured before `_apply_selection`.** The pick updates in place, so
  afterwards nothing distinguishes a claim from a move.
- **The pick alert sends inline**, matching `notify_member_joined` — up to eleven webpush
  calls on the submit path. Accepted, not overlooked: moving delivery off the request is a
  delivery-layer change. **Reach is 5 active subscriptions across 13 profiles**, so most of
  the 132-sends-per-round volume does not land today. Revisit before subscriptions grow.
- **`current_open_gameweeks` is now orphaned** — no caller in `src`. Kept because removing
  it forces timing rewrites in two tests whose subjects are elsewhere; its docstring says
  so and it is a fair removal candidate.
- **The picks-open trigger is dead code in 2-1 Hibs** until `pick_open_offset_minutes` is
  set on that league — its rounds are born `open` at discovery, so `open_due_gameweeks`
  never moves one. Correct for `the-coupon`, which carries the offset.

**Next:** `docs/BUILD_PLAN.md` has no unchecked batches. Owed: `/ship-prod`, and the
Batch 74 production run.

### Batch 74 — applied to production 2026-08-26
`--dry-run`, then `--apply` at 06:13:41 UTC, then an independent read to verify rather than
trusting the run's own output. 2-1 Hibs now reads Gameweek 1-4 in date order; the three
profiles carry their new names; **36 picks and 12 memberships untouched**. A second
`--apply` reported every row `==`, proving idempotency against production and not only in
a test.

- **`Craig` and both members' old names are now free for anyone to register.** Renaming releases a
  name outright, unlike deleting a member — see the Batch 74 notes above.
- **The three have not been told.** Nobody was signed out (the JWT subject is the player
  id), so this only bites at the next sign-in or a PIN reset.
- The right path to production from this Mac is a **direct asyncpg connection**, DSN pulled
  from `railway variables --kv` into a file that never reaches context. **Not the Supabase
  MCP** — that points at `wc2026-predictor`, a different product, and its timeouts read
  exactly like a Coupon outage.

### 2026-08-26 — production configuration change, and Batch 77 written
The owner set `pick_open_offset_minutes = 720` on 2-1 Hibs. `rederive_claim_periods`
restamped Gameweek 4 correctly (`picks_open_at_utc = 2026-08-29 02:00`, twelve hours
before its 13:30 lock) and left `status = 'open'`.

- **This is Batch 73's scenario hit for real, and the fix held.** Picks were refused
  throughout (`pick_refusal` -> `PICKS_NOT_OPEN`, GW4 had zero picks) and the badge read
  "Not open". Nothing member-visible was wrong.
- **What was wrong was invisible.** `open_due_gameweeks` selects `status == scheduled`
  only, so it could never have fired Batch 76's picks-open notification for that round.
  A silent loss: refusal correct, badge correct, push absent.
- **`rederive_claim_periods`' own comment (`gameweek.py:208`) is half wrong.** It says
  status is not re-derived because `open_due_gameweeks` "re-labels on its next run". It
  does not. The *other* half of that comment is sound and must survive — a round holding
  picks must not be told it has not opened. That split is the whole design of Batch 77.
- **The owner asked for GW4 to be set to `locked`; that would have killed the round.**
  `pick_refusal` treats any status outside `scheduled`/`open` as terminally shut, so
  `locked` means unpickable forever, not "not open yet". Set to **`scheduled`** instead,
  guarded on `status='open'` + future `picks_open_at_utc` + zero picks. **"Locked" in this
  product is not the plain-English word** — check before honouring it.
- **The direct asyncpg route died mid-session.** The Supabase host is IPv6-only and this
  Mac's IPv6 route disappeared between the deploy and this change; `host` still resolved
  it while Python's `getaddrinfo` failed for both families. Fell back to `railway ssh`
  with a base64-uploaded script, which worked. **Both paths are worth keeping in mind —
  neither is reliably available.**

**Next:** Batch 77 — have `rederive_claim_periods` re-derive `status` where no picks exist.

## Batch 77 — A round stays labelled `open` before it has opened, and the notification pays for it
**Commits:** c435179 · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The backwards transition is deliberately narrower than re-deriving lifecycle state.**
  Only an `open` round whose newly stamped opening is in the future and which holds no
  pick becomes `scheduled`; dropping an opening does not move `scheduled -> open`.
- **A pick of any status protects the old label.** The service reads all picked gameweek
  ids in one indexed query rather than issuing one existence query per round, and logs at
  info when it declines the transition.
- **The unchanged-instant early return survives.** This fixes the state when a settings
  edit restamps the round; it does not turn `rederive_claim_periods` into a general repair
  sweep for an already-stale row whose instants did not move.
- **No monotonic-status dependency was found.** Numbering ignores status; selection and
  current-round ordering treat `scheduled` and `open` as the same pickable class; locking
  covers both; and settlement is driven by time and terminal state.
- **`/ship-prod` is owed.** Merging `main` deploys no material web change for this
  API-only batch, while Railway keeps the old `rederive_claim_periods` until explicitly
  shipped.

**Next:** Launch phase L5 — launch and first-Saturday watch; ship the Batch 77 API change.

## Batch 78 — Your pick, the combined coupon and the results are three names for one list
**Commits:** dfe55a9 · verified: `scripts/ci-local.sh` PASS (11 checks), 727 frontend tests

### Key facts for future sessions
- **`PickRow` is now the only row in the coupon section**, and its `lead` prop is the
  whole design: `player` for the roster (who has picked), `selection` for the acca (what
  is riding on it). Same facts, opposite hierarchy. Adding a fact to one list means
  adding it to `PickEntry`, not to a component.
- **Two differences between the two lists are real and are kept.** A roster entry can
  have `selection: null` — a member who picked nothing appears nowhere in the slate, which
  is the roster's entire reason to exist — and a leg can carry settlement. That is why
  `PickEntry` has a nullable selection and optional status/points/score rather than there
  being two types.
- **The Season tab is still routed at `/results`.** Only the label and the page title
  changed; `predictionsPath(slug, '/results')` and every existing link are untouched,
  because members have the URL in their history.
- **`GameweekNav` no longer prints a fixture-denominated fraction.** Anything wanting
  "picks over members" must read the roster, which is the only place that denominator
  exists on the client; `GameweekSummary` carries no member count.
- **The e2e flow was a real constraint, not just a check.** `coupon-flow.spec.ts` pins
  `my-pick-summary`, `member-roster` ("2 of 3 picked", "1 to go", "Yet to pick") and
  `acca-leg-N`, so those testids and strings survived the refactor deliberately.

**Next:** Batch 79 — the settled week reaching the home card, and the rank history under it.

## Batch 79 — The week ends and home has nothing to say about it
**Commits:** 1c6aaf9 · verified: `scripts/ci-local.sh` PASS (11 checks), 734 frontend tests, 8 new Postgres-backed tests

### Key facts for future sessions
- **Never read a settled round off `current_round`.** `accepting_picks` treats a NULL
  `picks_open_at_utc` as open *now*, so on a league announcing no opening the next round
  outranks the settled one from the moment discovery writes it. Anything about "the week
  just gone" needs its own query; `last_result` is that query.
- **`standings_by_league` now takes `exclude_gameweek_ids`, and the exclusion is in the
  JOIN.** In a `WHERE` it would drop members whose only pick was in the excluded round
  instead of ranking them at zero. This is the rank-history mechanism — there is still no
  snapshot table and `models/standing.py` remains the *football club* table.
- **The summary is nine fixed queries now, not five**, and the docstring says so. All
  four additions are set-based; adding a sixth league still adds rows, not round trips.
- **`points_awarded is None` is not zero.** A void pick scored nothing because it never
  ran; the card says "was void" and prints no points, which is the same distinction
  `picks_played` vs `picks_priced` exists to keep on the leaderboard.
- **Batch 80 consumes this batch's read.** Per-player per-round history for the form line
  is the same rows the rank cutoff walks — write it once, in `scoring.py`.
- **A `/ship-prod` is owed.** Every new field is optional with a default, so the pushed
  web app renders exactly as before until Railway ships the API.

**Next:** Batch 80 — form on the leaderboard.

## Batch 80 — A leaderboard that cannot tell a hot streak from a season average
**Commits:** ea7f1e3 · verified: `scripts/ci-local.sh` PASS (11 checks), 741 frontend tests, 7 new Postgres-backed tests

### Key facts for future sessions
- **`PickFormLine` is not `FormLine` and must not be merged into it.** `FormResult` is a
  football club's W/D/L; a coupon pick is won/lost/void. A void fixture never ran, which
  is the same distinction `picks_played` vs `picks_priced` protects — collapsing it into
  `D` would undo Batch 70 in its most visible place.
- **`with_form` is off by default in `standings_by_league`.** `routers/me.py` calls it
  twice per request to difference two tables and renders no run, so it must not pay for
  one. `standings()` passes True, which is how the leaderboard *and* the player profile
  get form from one change.
- **The batched-vs-single equality invariant now reads "given the same `with_form`".**
  `test_standings_by_league_keeps_leagues_apart` asserts both halves; if you ever make
  form unconditional, that test is the one that will tell you honestly.
- **The run is sliced server-side** by `row_number()` partitioned on (league, player), so
  a leaderboard costs two queries whatever the size of the league *or* the length of the
  season. There is a test asserting exactly two SELECTs.
- **Order is newest-first on the wire, oldest-first on screen** — the same contract every
  other form payload here follows, so the nth pip is the nth row of any panel.
- **`PerLeagueSummary` deliberately does not carry form.** Home gained Batch 79's result
  panel instead; adding a run there was considered and declined rather than missed.

**Next:** `/ship-prod` for Batches 79-80, then Launch phase L5.

## Batch 81 — Form stops at the leaderboard, and home is where the member actually looks
**Commits:** 7fa75da · verified: `scripts/ci-local.sh` PASS (11 checks), 744 frontend tests

### Key facts for future sessions
- **`with_form` now defaults to `True`, and there is exactly one caller passing `False`:**
  the `exclude_gameweek_ids` call in `routers/me.py` that rewinds the table to difference
  two ranks. Any table that gets drawn carries form. If you add a third caller, ask
  whether it renders before turning the run off.
- **Never put `PickFormLine` inside a link.** It is a `role="img"` with an `aria-label`
  spelling the run out in words, so the whole sentence is appended to the link's
  accessible name. `DashboardPage.test.tsx` walks every link on the page asserting this.
- **Form implies a last result.** Both derive from a settled round holding that member's
  pick, so hanging the run inside `LastResultPanel` cannot hide it. That implication is
  load-bearing for where it is drawn.
- **`PerLeagueSummary.recent_form` is read straight off the league's season table**, the
  same `Standing` the leaderboard renders, so home and the leaderboard cannot disagree
  about the same member's run.
- **This reversed a Batch 80 decision, it did not fix a defect.** The session log entry
  above still records the original reasoning; the half that survived is that the throwaway
  table should not pay for a run.

**Next:** `/ship-prod` for Batches 79-81, then Launch phase L5.

## Batch 82 — Push subscriptions trust the endpoint an anonymous caller hands them
**Commits:** 82b4b14 · verified: `scripts/ci-local.sh` PASS (11 checks), green first attempt

### Key facts for future sessions
- **The allowlist is the control; the private-range check is not.** No RFC1918 literal can
  also be `fcm.googleapis.com`, so the IP check can never be the thing that saves us. It
  stays because it makes the refusal reason honest, and because if anyone ever widens the
  host rules the loopback guard is already there.
- **`urlsplit(...).hostname` is what makes the bypasses fail**, not the allowlist itself.
  It resolves userinfo (`https://fcm.googleapis.com@evil.example/`), lowercases, and drops
  the IPv6 brackets. Comparing against the raw string would pass all three of those.
- **`*.notify.windows.com` is a suffix match and must keep its leading dot.** WNS shards
  the host per-datacentre (`par02p.notify.windows.com`), so it cannot be an exact match —
  but `endswith("notify.windows.com")` would also accept
  `notify.windows.com.evil.example`. There is a test for exactly that string.
- **`/push/unsubscribe` is deliberately unvalidated.** It only ever deactivates a row the
  caller already owns, and tightening it would reject the removal of a subscription stored
  before this batch. The SSRF sink is subscribe, because subscribe is what delivery reads.
- **The existing happy-path test used `https://fcm.example/push/abc`** — a placeholder, not
  a push service — so this batch had to move that fixture to a real FCM endpoint. Delivery
  tests still use the placeholder (`_sub()`), which is fine: they never re-enter validation.
- **This is API-only and Group A owes one `/ship-prod` at its end** (Batches 82-85). Nothing
  here reaches members on the close-out push; the endpoint stays open in production until
  that ship runs.

**Next:** Batch 83 — the case-variant registration race (needs a migration).

## Batch 83 — Two concurrent registrations for case-variant names both succeed
**Commits:** 811bea0 · verified: `scripts/ci-local.sh` PASS (11 checks) — **red on the first
attempt**, see below

### Gate failures and how they were fixed
- **`test_logging_config.py::test_an_odds_call_publishes_no_key_even_with_httpx_logging_on`
  failed on the first full-gate run**, asserting `"HTTP Request" in output` against an
  empty stream. It passed alone and passed on `main`, so it was not a pre-existing red.
  Cause: `migrations/env.py:20` calls `fileConfig(config.config_file_name)`, and
  `logging.config.fileConfig` defaults to `disable_existing_loggers=True` — so running a
  migration **in-process** sets `disabled = True` on `httpx` for the rest of the session.
  Fixed by restoring the flags in the new test module, not by touching the logging test.

### Key facts for future sessions
- **Any new test file that runs alembic in-process and sorts before `test_logging_config.py`
  will break the suite.** `test_migration_012` and `test_migration_014` have leaked this
  since they were written; they are only safe because `m` > `l`. The real fix is
  `disable_existing_loggers=False` in `migrations/env.py`, which is outside this batch.
- **The index is `uq_profiles_display_name_lower`, not a constraint.** Postgres cannot
  express `UNIQUE (lower(col))` as a table constraint, so `op.drop_constraint` will not
  find it — a later migration touching it must use `op.drop_index`.
- **017 refuses to run on a database that already holds a collision, and names the rows.**
  That check is hand-written rather than left to the unique violation, because this
  migration runs on boot: "duplicate key value" in a container log does not say which
  member to rename, and the service stays down until somebody works it out.
- **017 was NOT verified against production data.** The prod Postgres host
  (`db.pugujiiojitstkilphrz.supabase.co`) has AAAA records only and this workstation has
  no IPv6 route; the project's REST API answers **402** under the egress quota. The
  runtime check is what stands in for it. **`/ship-prod` is the first time this migration
  meets real data** — if the API fails to boot, read the error, it names the profiles.
- **The Supabase MCP server is not production** and must not be pointed at it —
  `ship-prod.md:12` records the prod project as "never to be attached to MCP". Its
  `execute_sql` timed out here, which is the right outcome.
- **The index covers soft-deleted rows deliberately**, matching the pre-check's own
  refusal to filter on `deleted_at`: a departed member's name stays reserved.
- **API-only. Group A still owes one `/ship-prod`** (82, 83, 84, 85).

**Next:** Batch 84 — reject a league window landing in the DST-transition hour.

## Batch 84 — A league's window can be configured to land on the DST-transition hour
**Commits:** e267e0b · verified: `scripts/ci-local.sh` PASS (11 checks), green first attempt

### Key facts for future sessions
- **The check runs in the handlers, not in `CreateLeagueRequest`/`UpdateLeagueRequest`**,
  which is where the finding put it. A PATCH naming only `slate_start_minute` is legal,
  and whether that minute is safe depends on the weekday already stored — the request body
  never sees it. `_check_claim_period` sits in the handlers for exactly this reason and
  says so; the new check is its neighbour.
- **Four instants are checked, not one.** Opening, close, lock, and announced opening are
  each built by the same wall-clock arithmetic. The lock is the interesting one: a Sunday
  03:00 window with a 90-minute lock is a *safe window with an unsafe lock*, which is why
  `_recurs_into_a_transition` normalises a possibly-negative minute onto its real weekday
  before testing it.
- **Transition days come from `zoneinfo`, by walking the year and sampling the offset at
  noon** — not from "the last Sunday of March". `test_transitions_are_read_from_zoneinfo_not_assumed`
  asserts what the tz database says, so if the UK ever changes the rule that test fails
  first and explains the others.
- **The rejected range is 01:00-01:59 on a Sunday, and it is rejected outright** rather
  than only for the two rounds a year that hit it. A weekly window recurs into both
  transitions, and a config that is silently wrong twice a year is the finding.
- **No existing league is affected.** The default is Saturday 15:00 with a 30-minute lock
  → Saturday 14:30, and there is a test pinning that. Validation is on write only, so a
  stored window is never re-judged on read and no league can be bricked by this.
- **API-only. Group A still owes one `/ship-prod`** (82, 83, 84, 85).

**Next:** Batch 85 — the last of Group A, then `/ship-prod`.

## Batch 85 — The "member joined" notification skips the per-league mute
**Commits:** c6e53eb · verified: `scripts/ci-local.sh` PASS (11 checks), green first attempt

### Key facts for future sessions
- **`league_id` is a required parameter on `notify_member_joined`, deliberately.** A
  default of `None` would have let a fourth call site reintroduce exactly the omission
  this batch fixes, silently and with no test failing. All four triggers now take it.
- **Nothing else about the notification changed.** No `url`, `data` or `tag` was added,
  so tapping it still does what it did — the other three triggers carry those and this one
  does not, which is a real inconsistency but not this batch's.
- **The mute test needed two admins.** Suppressing *everything* passes a one-admin test
  just as well as suppressing the right one, so the muted and unmuted admin are both in
  the same league and the assertion is `push.call_count == 1`.
- **`_profile` in `test_notification_batch_76.py` now takes `role=`**, defaulting to
  `player` so every existing caller is untouched. `notify_member_joined` notifies site
  admins, so the test needed profiles the other triggers' tests never did.
- **Group A is complete (82, 83, 84, 85) and every batch in it is API-only.** The
  `/ship-prod` at this boundary is the one that carries all four to members, and it
  applies **migration 017**.

**Next:** `/ship-prod` for Group A, then Group B (Batches 86, 88, 87 — web only, no ship).

## Shipment 2026-08-27 — Group A (Batches 82-85) to production
**Commits:** `3cb8b4f1` · Railway `caeb17c2-732c-4195-9322-e7b84e7db3d8` · migration `016` → **`017`**

### Key facts for future sessions
- **There is no usable API rollback baseline until the next migration-free shipment.**
  `a8ab5234` is recorded as the previous healthy deployment but bundles revisions `001`-`016`
  only, so against a database stamped `017` its Alembic fails before uvicorn. Forward-only,
  as after `012`, `013` and `014`/`015`.
- **017's precondition was unverifiable beforehand and resolved clean.** The upgrade running
  at all is the proof no case-variant collision existed; confirmed afterwards inside the
  container. The migration's own pre-flight check was what made shipping it defensible
  without that check — an abort would have left production untouched on `a8ab5234`.
- **`railway ssh` + `psql` is the only path from this workstation to the production
  database.** Direct `asyncpg` no longer works: the host publishes AAAA records only and
  this Mac has no IPv6 route (`getaddrinfo` raises). The REST API is not an alternative —
  it answers **402** under the egress quota. Strip `+asyncpg` from the scheme *and* the
  `?ssl=` query before handing the URL to psql, and never let it reach stdout.
- **Section 4 (Vercel) was skipped by design again.** The GitHub integration had already
  built `3cb8b4f1` and held the stable alias; confirmed by reading `githubCommitSha` off the
  Vercel API, never from timing.
- **The committed header set is exactly three** — `X-Content-Type-Options`,
  `Referrer-Policy`, `Permissions-Policy` (`apps/web/vercel.json`). HSTS is Vercel's own.
  No CSP and no `X-Frame-Options` is committed, so their absence is not a regression.
- **The 0.25 vCPU / 500 MB limits are still unverifiable** — the same dead end as
  2026-08-26. `railway.toml` does not declare them and the CLI-reachable GraphQL schema
  rejects `cpuLimit`/`memoryLimit` on `serviceInstance`. Everything it *does* declare
  verified against the deployment manifest.
- **Batch 82's fix was not probed in production** — that needs an authenticated account and
  writes a row. It rests on the gate's 17 tests.

**Next:** Group B — Batches 86, 88, 87 (web only, no `/ship-prod` owed). 86 and 88 touch the
same two files, so run them adjacent; 88 unblocks Group H.

## Batch 86 — Login and registration are the only screens with no landmark or heading
**Commits:** `3e33c17` · verified: `scripts/ci-local.sh` PASS (11 checks) — ruff, ruff format,
mypy, alembic + pytest, deployment-config, pnpm install --frozen-lockfile, lint, typecheck,
test, build, playwright prod-bundle

### Key facts for future sessions
- **jsdom cannot verify `landmark-one-main` or `page-has-heading-one` — at all.** Both
  resolve through axe's visibility check, which needs layout, and jsdom reports zero
  dimensions for everything. Measured on this suite: no `<main>` and no `<h1>` returns the
  same `incomplete` verdict as a correct page *and* as a page with three `<main>`s. Any
  jsdom assertion on these two rules is green regardless of markup. They are now checked in
  a real browser by `apps/web/e2e/prod-bundle-a11y.spec.ts`, which runs inside ci-local's
  existing prod-bundle step. `region` is the one UX-07 rule jsdom does decide, and it covers
  22 of the finding's 26 nodes.
- **`jest-axe` silently corrupts the DOM for any context outside `<body>`.** Its `mount()`
  (10.0.0) falls back to `document.body.innerHTML = element.outerHTML`, which re-roots the
  axe context at `<body>` — so page-level rules are skipped — and replaces React's live
  container with a string clone, leaving Testing Library's auto-cleanup holding a detached
  node. Each such test then leaks its rendered page into the next; four cases accumulated
  four `<main>`s. Call `axe-core` directly for anything page-level. `axe-core` is now a
  direct devDependency (4.10.2, the review's version, already resolved transitively).
- **axe's landmark rules only ask whether *at least one* exists.** `landmark-one-main` passes
  a page with three `<main>`s and `page-has-heading-one` passes three `<h1>`s, despite the
  names. The explicit count assertions in both suites are what actually pin "exactly one",
  and they are what caught the cleanup leak above.
- **`CardTitle` is hard-coded to `<h2>` and was deliberately left alone.** The two pages
  render an `<h1>` carrying `CardTitle`'s own classes plus the card's, so the rendered type
  is unchanged — 18px / 600 / 22.5px / -0.45px, confirmed in the browser. Changing the
  shared component would have reached every card in the app.
- **`/register` shows the install gate, not the form, at mobile widths.** `BrowserOnboarding`
  intercepts it, so a mobile-viewport check of that route sees "Once the app is installed…".
  The e2e spec runs at Desktop Chrome's viewport, where the form renders. Not a Batch 86
  concern, but it will mislead any future mobile screenshot of that route.
- **Four more pages share the same unfixed shell** — `JoinPage`, `ForgotPinPage`,
  `SetPinPage`, `WelcomePage` all use the identical `min-h-screen … justify-center` `<div>`
  with no `<main>` and no `<h1>`. The 2026-08-26 sweep only covered `/login` and `/register`,
  and Batch 86's scope boundary is those two, so the other four are untouched and still
  carry the defect.

**Next:** Batch 88 — harden the `?next=` redirect guard against the `/\evil.com` backslash
bypass, in the same two files this batch just reshaped.

## Batch 88 — The login/register redirect guard misses the backslash open-redirect bypass
**Commits:** `ba2c58a` · verified: `scripts/ci-local.sh` PASS (11 checks), plus an
end-to-end drive of the production bundle in Chromium

### Key facts for future sessions
- **OPS-08's mechanism is no longer "plausible" — it is confirmed.** The review could not
  test it live. Chromium resolves `/\evil.com`, `/\/evil.com` *and* `/\\evil.com` all to
  `http://evil.com/`, and the old `startsWith('/') && !startsWith('//')` predicate accepted
  every one. Driven end-to-end against the built bundle with the login call stubbed, a
  sign-in from `/login?next=/\evil.com` lands on `/` and stays on origin, and
  `?next=/join/ABC123` still delivers the invite.
- **The guard resolves rather than pattern-matches.** `lib/redirect.ts` hands the value to
  `new URL(requested, origin)` and keeps it only if `.origin` held, so the decision belongs
  to the same parser the browser will use — no list of hostile shapes to keep ahead of. It
  returns the *parsed* path, not the caller's string, so react-router cannot resolve
  something different from what was validated.
- **The leading `/` check is load-bearing and must stay.** Without it a bare `evil.com`
  resolves to the same-origin path `/evil.com` and passes the origin comparison. Every
  `?next=` this app issues is an absolute path.
- **Reverting the helper to the old predicate fails exactly 11 tests** — 7 in
  `redirect.test.ts`, 4 across the two page suites — and nothing else. That asymmetry is
  the evidence the rewrite closed the gap without loosening what already held; re-run it
  that way if the guard is ever touched again.
- **`RegisterPage.test.tsx` mocks `useNavigate` globally; `LoginPage.test.tsx` does not.**
  So Register asserts on the `navigate` spy and Login asserts on a `LocationProbe` reading
  the real router location. A location probe in the Register suite would never update.
- **Batch 102 (react-router 7) is now unblocked.** It remains the complete upstream fix;
  this guard is independent of it and should survive the migration unchanged.

**Next:** Batch 87 — stop the service worker caching authenticated `/api/v1/*` JSON the
server marked `no-store`. Last of Group B; still no `/ship-prod` owed.

## Batch 87 — The service worker caches authenticated JSON the server marked `no-store`
**Commits:** `80022d2` · verified: `scripts/ci-local.sh` PASS (11 checks); guard confirmed
present in the built `dist/sw.js`

### Key facts for future sessions
- **SEC-13's second suggested fix would not have worked.** The review offered "drop
  `CacheableResponsePlugin` for `/api/v1/*` and rely on `NetworkFirst`'s in-flight fallback
  without persisting to Cache Storage". `NetworkFirst` persists by *default*;
  `CacheableResponsePlugin` only ever narrows what it persists, so removing it caches
  strictly more. Preventing the write needs `cacheWillUpdate` returning `null` — nothing
  else in the plugin list can stop it.
- **API reads no longer survive going offline.** Every API response carries `no-store`
  (`middleware.py:64`, unconditional), so the `api-coupon` cache now holds nothing and the
  route is network-with-a-3s-timeout. A flaky connection mid-Saturday reaches the app's
  offline state rather than an up-to-hour-old league table. That is the review's intended
  trade and `OfflineBanner` covers it, but it is a real behaviour change and the first
  place to look if someone reports "the standings used to work on the train".
- **The guard reads the header rather than deleting the route**, so if any endpoint is ever
  served without `no-store` it starts being cached again automatically. That is deliberate:
  the alternative silently strands a future cacheable response with nothing pointing at why.
- **Workbox strategies cannot run under jsdom without two stub globals.**
  `Strategy.handleAll` does `options instanceof FetchEvent` and `StrategyHandler` asserts
  `options.event instanceof ExtendableEvent`. Bare classes satisfy both, and the event must
  be a real instance of the stubbed `ExtendableEvent`, not a cast object literal.
- **`ExpirationPlugin` cannot be in a jsdom test harness.** It writes timestamps to
  IndexedDB from `cacheDidUpdate`; jsdom has none, and the unhandled rejection exits the
  run non-zero *while every test still reports as passing* — 8 passed, exit 1. Worth
  remembering as a shape: a green test list is not a green run.
- **The cache write lands in a `waitUntil` promise**, so an assertion made straight after
  `strategy.handle()` sees an empty cache whether or not the guard works. The harness
  collects and awaits them, which is what makes the negative result mean anything.

**Next:** Group B is complete. Group C — Batches 89, 90 (API + web, `/ship-prod` owed at
the boundary, and the review's highest-value product finding).

## Batch 89 — Pick submission has a per-member limit but no aggregate one
**Commits:** 88458ef · verified: `scripts/ci-local.sh` PASS (11 checks), green first run

### Key facts for future sessions
- **The bound is `50/hour;100/day` per league, and 50 was not a free choice.** It is
  simultaneously what the hour leaves after the measured peak browsing hour
  (`100 − 28 = 72`) and `max_members`'s ceiling, so a full league can still take one pick
  each. Any tightening below 50 refuses legitimate claims from a full league; any
  loosening past 72 outspends the plan.
- **This bound deliberately does *not* reserve the ad-hoc round allowance, and the
  per-member one does.** `test_one_member_cannot_exhaust_the_plan_by_changing_their_mind`
  measures against `100 − 28 − 60 = 12` because it asks whether one actor can break the
  budget alone. The aggregate test measures against 72 because reserving an admin
  button's untaken 60 against members submitting picks would refuse real claims to
  protect a press that is not happening. Both framings are stated in the tests; do not
  "fix" the inconsistency without reading them.
- **The bucket counts submissions, not upstream requests.** A submission prices one
  event and one event is one request, so bounding submissions bounds spend without
  needing to know whether this fetch hit the 60s cache. It over-counts a same-fixture
  re-pick inside a minute and never under-counts — the safe direction.
- **Keyed per league, so it bounds a league and not the installation.** Two concurrent
  full-tilt leagues put the global plan back in charge.
  `test_the_aggregate_bound_is_per_league_rather_than_per_installation` is the tripwire
  and will fail loudly if the limit or the plan moves.
- **The charge sits after the free refusals and before `_snapshot_selection`.** A pick
  refused for lock or an unoffered market has spent nothing; everything below the fetch —
  including a lost claim race — has. Batch 57's lock-then-fetch ordering is untouched.
- **`PICKS_BUSY` has no client-side copy yet.** `pickErrorMessage` falls through to the
  raw code. Batch 90 owns it, and no member can see it before then because the API does
  not ship until `/ship-prod`.

**Next:** Batch 90 — pick submission's offline resilience, which must render `PICKS_BUSY`
alongside offline and lost-the-race. Then `/ship-prod` at the Group C boundary.

## Batch 90 — Pick submission has no offline resilience
**Commits:** cea2353 · verified: `scripts/ci-local.sh` PASS (11 checks) after one fix

### Key facts for future sessions
- **The whole design rests on one distinction: was the request *started*?**
  `NetworkError.mayHaveLanded` is `false` only when `apiFetch` refused to call `fetch`
  because `navigator.onLine` was false. Everything else — a dropped connection, our own
  12s timeout — is `true`. `navigator.onLine` is trusted only in the negative; `true`
  means "there is an interface", not "the server is reachable", so it proves a request
  never left and never promises one will arrive.
- **`unconfirmed` is never re-sent automatically, and that is the batch.** The server
  updates a pick in place, so re-sending is safe *for that submission* — the harm is a
  member who has since picked something else having their claim silently taken backwards.
  Recovery is a `GET .../pick`, which changes nothing.
- **The queue is a single slot, not a log.** One pick per member per round means only the
  newest intent can be right, so `submit` drops whatever was held before sending. This is
  what makes the reconnect flush safe; a FIFO here would be a bug.
- **In memory only — no IndexedDB, no Background Sync.** Deliberate, given SEC-13/Batch 87.
  An unsent pick is the member's own intent and holds nobody else's league data, but a
  persisted one firing after a sign-out on a shared phone is worse than the case it
  covers. Also sidesteps the `ExpirationPlugin`/jsdom hazard Batch 87 hit.
- **`vi.mocked(toast)` does not type its members as mocks.** `mockToast.error.mock.calls`
  typechecks nowhere — reach the log through `vi.mocked(toast.error).mock.calls`. This is
  what turned the gate red; `pnpm test` was green while `typecheck` and `build` failed, so
  a green test list again did not mean a green run.
- **`apiFetch`'s offline short-circuit applies to every call, not just picks.** An offline
  read now raises `NetworkError('You are offline')` instead of attempting a doomed fetch.
  Nothing in the suite depended on the old shape, but it is a global behaviour change.
- **Batch 90's own BUILD_PLAN row carries a premise Batch 87 falsified** — "Reads already
  get a resilient Workbox `NetworkFirst` cache with an offline fallback". They do not; the
  `api-coupon` cache holds nothing since `no-store` is honoured. The finding still stood
  (the write path had no resilience) but the row's contrast no longer describes the app.

**Next:** `/ship-prod` — Group C's boundary. Batch 90's client is live in front of members
on this push while Batch 89's `PICKS_BUSY` does not exist in production until the API
ships. Then Group D (Batches 99, 100, 101, 95).

## Batch 99 — Every rate limit resets on redeploy
**Commits:** 093e64f · verified: `scripts/ci-local.sh` PASS (11 checks), green first run

### Key facts for future sessions
- **The split is now asserted in both directions, and that is most of the batch.**
  `/auth/login` and `/auth/pin/reset-request` charge Postgres; `PICK_SUBMIT_SHARED_LIMIT`,
  `PROVIDER_SLATE_FETCH_LIMIT` and `PICK_SUBMIT_LIMIT` deliberately do not, and
  `test_durable_rate_limit.py` fails if either half moves. Anyone migrating a provider
  budget to the table is reversing a decision, not filling a gap.
- **The durable counter runs on its own session (`get_limiter_db`), not the request's.**
  Login for an unknown display name returns 401 having committed nothing at all — counted
  on the handler's session the attempt would vanish with the transaction and name
  enumeration would be free. That is why the two routes swapped `@limiter.limit` for a
  dependency rather than keeping the decorator: the charge is `await`ed, and `slowapi`'s
  `Limiter.hit` is synchronous.
- **The 429 body is unchanged and had to be.** `enforce_durable_limit` raises slowapi's own
  `RateLimitExceeded` and sets `request.state.view_rate_limit` by hand, because
  `_rate_limit_exceeded_handler` reads that attribute unconditionally and `AuthContext.tsx`
  branches on `{"error": ...}`; a 429 carrying `detail` would read as "your details are
  wrong" and invite the retry the limit just refused.
- **`login_key` reads `display_name` from the raw body, before pydantic.** In memory that
  was merely wasteful; against a `String(200)` column a ten-kilobyte name is a `DataError`
  and a 500 on the endpoint an attacker is already probing. `durable_bucket_key` keeps a
  readable prefix and appends a SHA-256 of the whole key, so folding cannot merge two
  callers into one bucket.
- **`conftest.py` now has a second autouse reset.** `limiter._storage.reset()` empties the
  in-process store only, so `reset_durable_rate_limits` truncates the table before and
  after every test when `DATABASE_URL` is set. Without it a DB-backed limit leaks across
  tests and surfaces as an unrelated module failing on somebody else's sixth login.
- **`test_auth.py`'s `_override_db` now stubs the limiter dependency too.** Every test in
  that module runs with no Postgres at all; leaving the durable limiter live would make
  ~30 hermetic tests open a real connection. The real behaviour is covered end-to-end in
  `test_durable_rate_limit.py`, which is Postgres-backed.
- **Migration 018 needs no forward recovery plan beyond "drop it".** Nothing reads
  `rate_limit_counters` except the limiter, and an empty table is exactly the state every
  process had after every restart before this batch — a rollback costs at most one window
  of counts, which is the behaviour being replaced rather than a regression against it.

**Next:** Batch 100 — the single-replica guard on migration-on-boot. Then 101, then 95
(soft-blocked on FEAT-A09 egress headroom). `/ship-prod` at the Group D boundary.

## Batch 100 — Migration-on-boot is safe only while nobody raises the replica count
**Commits:** 5cd3af9 · verified: `scripts/ci-local.sh` PASS (11 checks), green first run

### Key facts for future sessions
- **The guard lives in `migrations/env.py`, not the start command.** `nixpacks.toml`'s
  chain was the obvious place and is the wrong one — it guards one invocation. In `env.py`
  it covers `railway run alembic`, a hand-typed upgrade and `/ship-prod` alike, and it
  cannot be dropped by someone editing the start command.
- **Railway exposes no replica *count* at runtime** — `RAILWAY_REPLICA_ID` is a UUID, not
  an ordinal — so the number is baked into the image by `nixpacks.toml`'s
  `DEPLOY_REPLICA_COUNT`, and `test_migration_guard.py` is what keeps that declaration
  equal to what `railway.toml` asks for. Raising replicas therefore takes two mistakes:
  change the declaration and ignore a red gate, and the boot still refuses.
- **`numReplicas` alone is the wrong field to read.** It is per-region; two regions at one
  replica each is two processes racing while `numReplicas` still reads 1. The effective
  count sums `multiRegionConfig`, and there is a test for that shape specifically.
- **The alembic tests are hermetic and prove *ordering*, not just refusal.** They point at
  `postgresql+asyncpg://...@127.0.0.1:1/nothing` — refused instantly rather than timed out
  — so at two replicas the run must fail with the guard's message and at one it must fail
  on the *connection*. A migration refused after connecting has already had its chance to
  race the one it was refusing.
- **Failing the boot is the decided behaviour, not a shortcut.** "Skip and let a designated
  instance own it" needs an instance ordinal Railway does not give. The refusal message
  names the release-step alternative and dates the decision, so whoever trips it finds the
  reasoning rather than re-deriving it.
- **No migration, so this batch does not strand the previous deployment.** Unlike Batch 99,
  the pre-`018` rollback question is unchanged by this one.

**Next:** Batch 101 — a defined failure trigger and alert for FotMob. Then Batch 95, which
is soft-blocked on FEAT-A09 egress headroom and an owner choice of storage destination.
`/ship-prod` at the Group D boundary.

## Batch 101 — Three shipped features rest on a provider whose terms forbid us, with no trigger
**Commits:** 477c1e5 · verified: `scripts/ci-local.sh` PASS (11 checks), green first run

### Key facts for future sessions
- **The trigger is three rules, and one of them is not a request-level signal at all.**
  401/403/451 fire on the first occurrence (the terms being applied, and they do not
  un-apply); everything else needs five consecutive failures with no success between; and
  a slate where *nothing* could be cross-checked fires immediately. The third exists
  because a source that answers `200` and carries none of our competitions fails no
  requests while verifying nothing — request health would never see it.
- **`verify_slate` fails open, which is correct and also silent.** A card nothing could be
  checked against is indistinguishable from a card that was fine. That is why the
  cross-check reports itself rather than being inferred, and why it is the loud one: it is
  the only FotMob dependency that decides whether a member's pick is valid.
- **Instrumented at `FotMobProvider._get`.** The one funnel every FotMob request goes
  through. A signal taken inside Football Stats or live scores would miss the outage
  whenever that feature happened not to be the one running — and only live scores runs
  every ten minutes.
- **The audit row is what the cooldown reads, not decoration.** An in-process timer would
  restart the noise on the first redeploy of a bad Saturday. Loud alerts get a one-hour
  window, quiet ones six. Same argument Batch 99 made for the login limiter.
- **Reported from `finally` in all three jobs.** A sweep that raised is exactly when the
  source is in trouble; the success path would lose the alert in the case it exists for.
  `test_a_job_that_threw_still_reports_what_the_source_did` is what holds that.
- **Roughly half the tests assert silence** — one timeout, four failures, a lone `429`, a
  success clearing the run, a slate with one checkable fixture. Eight of one real
  Saturday's fixtures were unverifiable by any available source, so alerting on partial
  coverage would fire every week and mean nothing.
- **The tracker is a module singleton and `conftest.py` resets it.** Same shape as
  `football_session`'s single client; without the reset a test that drives five failed
  requests leaves the next one starting from an alert already raised.
- **Migration 019 is an enum value** (`action_type` gains `football_provider_degraded`),
  added with `ALTER TYPE … ADD VALUE IF NOT EXISTS` as 012 did. The downgrade has to
  rebuild the type — PostgreSQL has no `DROP VALUE` — mapping any row holding it to
  `backup_failed`.

**Next:** Batch 95 — durable off-box logical backups, which is **soft-blocked**: it needs
Supabase egress headroom established for FEAT-A09 first, and an owner decision on the
storage destination (S3 / R2 / Backblaze). Then `/ship-prod` for Group D.

## Batch 102 — react-router 6 has no patch for its open-redirect advisory
**Commits:** 80e07a4 · verified: `scripts/ci-local.sh` PASS (11 checks) after one environment rerun

### Key facts for future sessions
- **The complete migration is the dependency and lockfile bump.** `react-router-dom` and
  `react-router` both resolve to 7.18.3, clearing the 6.x-only advisories and removing
  `@remix-run/router`; the repository already satisfies v7's Node 20 / React 18 floors.
- **There is no data-router migration hidden here.** The app uses declarative
  `BrowserRouter`/`Routes` only — no loaders, actions, fetchers or `RouterProvider` — and
  all lazy route declarations are module-scoped, so v7 forced no source compatibility
  changes.
- **Keep the `react-router-dom` imports.** V7 still supports that package; moving 61
  production/test imports to `react-router` would also churn Vite's manual chunk and is
  optional v8 preparation, outside this batch's no-redesign boundary.
- **Batch 88 remains defense in depth.** Its login/register redirect suites passed 56/56
  on v7, including both backslash forms; the app-owned URL-parser guard still normalizes
  attacker-controlled `?next=` before navigation.
- **The supplemental production audit is clean for React Router, not globally green.**
  It still reports pre-existing Nano ID/PostCSS findings through Tailwind; those are
  unrelated to this migration and were not folded into it.
- **The first full gate run failed before pytest on the host locale.** macOS has no
  `C.UTF-8`, so `pgserver initdb` refused it; rerunning the whole gate with
  `LC_ALL=LANG=en_US.UTF-8` passed all 11 checks, including the prod-bundle deep-link
  smoke. This was an environment reset, not a code fix.

**Next:** Batch 91 — make new leagues invite-only by default and explain every privacy
option at the point of creation. Batch 102 is web-only, so it creates no `/ship-prod`
obligation.

## Batch 91 — New leagues default to fully open with no explanation
**Commits:** ebdf774 · verified: `scripts/ci-local.sh` PASS (11 checks), green first run

### Key facts for future sessions
- **The API already defaulted to invite-only.** `CreateLeagueRequest.privacy =
  LeaguePrivacy.private` (`routers/leagues.py:326`) has been the server default all along;
  only `CreateLeaguePage` overrode it with `public_open`. This batch removes a divergence
  rather than setting a new policy, so no API change was needed and none was made.
- **The copy is grounded in the router, not in the option names.** `private` is excluded
  from `/discover` (the filter lists only the two public values) and refuses slug joins
  with `PRIVATE_LEAGUE`; `public_open` joins instantly; `public_request` creates a request
  the admin approves. Re-verify against `routers/leagues.py` before editing this copy.
- **A private league is not sealed — the join code still admits anyone holding it.**
  `join_league_by_code` (`routers/league_memberships.py:120`) never reads `privacy`, which
  is why the help text says "only people you send the join code to" rather than "invite
  only" as a security claim.
- **Selector copy lives in `CreateLeaguePage`, deliberately.** `PRIVACY_LABELS` in
  `lib/leagues.ts` is shared with `MyLeaguesPage` and `DiscoverLeaguesPage`, so changing it
  would have moved copy on screens outside this batch's scope boundary.
- **`LeagueSettingsPage` still has the unexplained dropdown**, and its stakes are higher:
  switching a league to `public_open` auto-approves every pending join request, and
  switching to `private` cancels them, with no warning in the UI. Out of scope here; left
  for its own batch.

**Next:** Batch 93 — the one-time rename notification, per Group E in
`docs/review/2026-08-26/07-sequencing.md` (91 → 93 → 94, then one `/ship-prod`). Batch 92
is numerically next but belongs to Group G. Batch 91 is web-only, so it reaches members on
this push and adds no `/ship-prod` obligation. **Nor does anything else: the live API is
`bc8c8191` at migration 019, which is Batch 101's close-out — Group D shipped, it just
never got a `docs: record the shipment` commit.** Reading the git log alone suggests
otherwise and is wrong; `scripts/check-deploy-drift.sh` (which reads `/api/v1/health`) is
the authority.

## Batch 93 — Three renamed members were never told
**Commits:** cb30011 · verified: `scripts/ci-local.sh` PASS (11 checks), green first run

### Key facts for future sessions
- **This product has no in-app notification inbox.** No `Notification` model, no
  notifications screen, no route — `send_notification` is web push and nothing else. So
  "notify a member" means "push to their active subscriptions", and a member without one
  cannot be reached at all. Anything specified as an in-app message needs that surface
  built first.
- **The trigger is `lifespan`, because a migration cannot send a push.** Delivery is an
  HTTP call per subscription; Alembic runs synchronous SQL. "On this batch's deploy"
  therefore means application startup, and the once-only guarantee Alembic's version table
  would have given for free is rebuilt from an `audit_log` row — Batch 101's pattern.
- **The marker is written only on delivery.** `send_notification` returns 0 for no
  subscription, a global mute, or quiet hours. None of those means the member was told, so
  no row is written and the next boot retries. The consequence is deliberate: this task
  keeps running until all three are reached, and it is cheap enough to (three indexed
  lookups).
- **A `pg_advisory_xact_lock` serialises it.** Batch 100's single-replica guard runs from
  `migrations/env.py` and covers migrations only — a lifespan hook is not migration code,
  and two containers booting together would both read "no marker" and both push.
- **Tests that patch `_send_push_sync` must patch the VAPID settings too.**
  `send_notification` returns 0 before it reaches the delivery call when
  `vapid_private_key`/`vapid_public_key` are unset, so a suppressed send is
  indistinguishable from a delivered one and the marker assertions pass for the wrong
  reason. `push_enabled()` in `tests/test_rename_notice.py` does both; this cost a red run.
- **Expected lifetime.** Once production holds three `display_name_changed` rows, the
  lifespan call and `services/rename_notice.py` can go. It is not a rename-notification
  feature — renaming a fourth member needs its own decision.

**Next:** Batch 94 — the league-scoped audit log, last in Group E, followed immediately by
`/ship-prod`. 94 is the asymmetry risk in the whole plan: a new
`GET /leagues/{slug}/audit-log` plus a page that calls it, where the page reaches members
on the close-out push and the route does not exist until the ship. Batch 93 is API-only and
adds **migration 020**, so it is not live until that ship either.

## Batch 94 — League admins have no audit-trail visibility into their own league
**Commits:** ee05026 · verified: `scripts/ci-local.sh` PASS (11 checks), green first run

### Key facts for future sessions
- **`audit_log` has no `league_id` column, and the writers disagree about `target_id`.**
  Nearly every league-scoped call site passes `target_id = league.id` *even when
  `target_table` names another table* (`league_memberships`, `league_join_requests`,
  `invites`). Two do not: `league_invite_revoked` records the **invite** id
  (`league_memberships.py:443`) and a league-scoped PIN reset records the **player** id
  (`credentials.py::pin_reset_audit`); both name the league in `changes.league_slug`.
- **So `_league_audit_scope` has two arms, and dropping either is a silent failure.**
  `target_id == league.id` alone omits every revoked invite and every admin-performed PIN
  reset — gaps in the one screen that claims to show what happened to the league. The
  `changes->>'league_slug'` arm alone would leak, which is what the cross-league test
  plants a foreign-slug row to catch. Anything that changes what the writers record should
  revisit this function.
- **Site-scoped rows (`{"scope": "site"}`) that name the league are included on purpose.**
  A site admin rotating a league's join code is an event in that league's history, and the
  row says who did it.
- **The response carries `changes`; the site dashboard's `AuditEntry` does not.** "A member
  was removed" is not what a league admin needs — "who removed whom" is. Everything in the
  payload is already about that league or its members.
- **`LeagueProvider` breaks a page test that does not stub `/api/v1/leagues/mine`.** It
  dereferences `leagues[0].slug` and throws before the page under test mounts, with a
  stack that points at the context rather than the test. Cost one red run.
- **Both halves ship together and must not sit apart.** The page reaches members on this
  close-out push; the route does not exist until `/ship-prod`, which is exactly the Batch
  51 / 2026-08-06 failure. Ship immediately.

**Next:** `/ship-prod` — the Group E boundary. It carries Batches 93 and 94 and applies
**migration 020**. After that, Group F (Batch 96, alone) or Group G (98, 97, 92); Batch 92
is the only earlier unchecked number and belongs to Group G.

## Batch 96 — "Season tables" that never start a new season
**Commits:** 0891762 · verified: `scripts/ci-local.sh` PASS (11 checks, green first run)

### Key facts for future sessions
- **The season definition spans two modules and neither is where the row said to look.**
  `season_for` / `current_season` are in `services/football_provider.py`; `season_bounds`
  is in `services/gameweek.py`. `scoring.py` now imports from both, which is safe:
  `gameweek.py` imports neither `scoring` nor `coupon`, so there is no cycle to create.
- **The boundary is in the `outerjoin` to `picks`, beside `exclude_gameweek_ids`, and that
  is load-bearing.** As a `WHERE` it would drop a member who did not play this season out
  of the table instead of showing them on nought. `recent_form_by_league` uses a plain
  `WHERE` for the same boundary and that asymmetry is correct — it returns runs keyed by
  member, not rows, so an absent member gets the empty run everyone gets.
- **No migration. Production stays at revision `020`,** so the recorded Railway rollback
  baseline is bootable for this shipment — the first time that has been true since Group C.
- **The boundary turned six existing test files date-fragile, and they are now anchored.**
  `tests/season_dates.py` holds the three helpers: `season_anchor` for rounds seeded
  relative to now, `season_week` for fixed offsets, `same_weekday_in_current_season` for
  the canned `SAMPLE_SATURDAY` slate. Anything that seeds a *settled* round and then reads
  a table must use one of them, or it will pass in August and fail in July.
- **`test_picks_flow` reads canned 2026 data, so it names its season.** `SAMPLE_SLATE_SEASON`
  is used at the two service-level standings reads; the four-surface agreement test instead
  seeds into the current season, because `/me/cross-league-summary` has no season parameter
  to name and making the other two name one would have made the agreement vacuous.
- **`rank_movement` is now `None` across a boundary rather than a confident zero.** The last
  result a league played can be June's while the table is already August's.

**Next:** `/ship-prod` — the Group F boundary, carrying the API half of Batch 96 with no
migration. After that, Group G (Batches 98, 97, 92).

## Batch 98 — Avatar initials use fill colours as text colours
**Commits:** f19249a · verified: `scripts/ci-local.sh` PASS (11 checks, green first run)

### Key facts for future sessions
- **Every avatar is a solid fill now.** The old 15%-tint treatment used the fill token as
  text too; the six entries in `AVATAR_PALETTE` now name the rendered background,
  foreground and Tailwind classes together so the test contract and component cannot drift.
- **Metal and bronze are the two theme-dependent foregrounds.** Both take near-black in
  dark mode and white in light mode; primary, accent, metal-dark and gold take the existing
  near-black on-fill ink in both. The weakest of all twelve pairs is light bronze at
  **4.93:1**, above the 4.5:1 normal-text floor.
- **The hash did not move.** `tintFor()` still uses the same name hash, modulo the same
  six-entry order, so a member keeps their established colour slot.
- **The browser flow now holds the visual acceptance.** After settling the seeded round it
  opens standings at 390×844, injects axe-core's `color-contrast` rule in dark and light,
  requires zero violations and saves a screenshot for each theme.
- **The one full Playwright flow passed first run.** The harness itself first hit the known
  macOS `initdb` locale failure and then two orchestration mistakes before the test ran;
  `LANG=LC_ALL=en_US.UTF-8` is the stable scratch-Postgres invocation. The code gate was
  green on its first and only run.

**Next:** Batch 97 — the home content and scale pass. Confirm the existing
`PerLeagueSummary` supplies what it needs before adding a route; if it remains web-only,
Batch 92 follows and Group G owes no `/ship-prod`.

## Batch 97 — Home stops a third of the way down the screen
**Commits:** 2744035 · verified: `scripts/ci-local.sh` PASS (11 checks, green first run)

### Key facts for future sessions
- **The row's example content was stale, not the page.** Batches 79 and 81 had already put
  every league, per-league opening/lock countdowns and recent results on home. Adding any of
  those again would have duplicated the cards. The existing cross-league response also
  carried aggregate season figures that home did not use, so no API route was needed.
- **The hero answers the cross-league question instead.** It finds every currently
  claimable league without the member's pick, sorts by that league's own lock and links to
  the earliest one. When nothing needs a pick it distinguishes all open picks being in from
  an upcoming opening or a genuinely quiet week.
- **Time still comes from stored UTC instants, not status or a shared Saturday.** The action
  applies the same `scheduled`/`open` plus opening/lock rule as each card and uses
  `parseInstant`; a test proves alphabetical API order cannot outrank the sooner deadline.
- **Only honest aggregate figures moved up.** Points, picks won/played and win rate span
  leagues on the same scale. Average rank stays on the career page because first of three
  and first of fifteen are not one comparable number without its coverage explanation.
- **The fill is content and scale, not min-height theatre.** A 218px hero, 32px greeting,
  larger action line, roomier cards/result panels and explicit leagues section put the
  sparse one-league settled view immediately above the tab bar at 390×844. Dark and light
  screenshots both passed a full axe sweep with zero violations.
- **One targeted test failed before the gate.** It read the always-mounted hero while the
  query was still loading; waiting for `home-season-summary` made it assert the loaded state
  it was written for. The production-preview flow and the full 11-check gate both passed on
  their first runs.

**Next:** Batch 92 — extend the existing clipboard-share pattern to settled results and
season-aware standings. It is Group G's final batch; with no API half added by 97, the group
still expects no `/ship-prod`.

## Batch 92 — A settled result can't be shared, only the pre-lock coupon can
**Commits:** d36edf3 · verified: `scripts/ci-local.sh` PASS (11 checks, green first run)

### Key facts for future sessions
- **Settlement has its own serializer now.** Open and locked coupons retain Batch 24's
  byte-for-byte text; settled rounds lead with the landed count and add final score,
  won/lost/void status and points to the same numbered, frozen-price format.
- **An unresolved score stays `home v away`.** Both goal values must exist before the share
  text prints `home X–Y away`; the name-based result join failing open must never become an
  invented nil-nil.
- **Standings sharing is bounded by the screen.** It copies the displayed response and the
  displayed season label. A `?season=2025` table therefore shares 2025/26 rows, never a
  merged all-time table or the current standings.
- **The clipboard path did not grow a second target.** Both new controls call
  `navigator.clipboard.writeText`; there is no native share sheet, URL payload or API half.
- **The visual flow passed in both themes.** Settled standings and result controls were
  checked at 390×844 with zero axe violations and four retained screenshots.
- **One harness launch used invalid `ENVIRONMENT=test`.** Pydantic correctly refused it;
  restarting the test-only API with the supported `development` value fixed the
  orchestration. The Playwright flow and full gate then passed first run.

**Next:** Batch 95 is the first unchecked batch and remains soft-blocked. The sequencing
addendum's next actionable group is Group I, Batch 103; it remains a separate batch.

## Batch 103 — The settings screen still asks for a privacy choice without saying what it does
**Commits:** 0132bfa · verified: `scripts/ci-local.sh` PASS (11 checks; locale-corrected rerun)

### Key facts for future sessions
- **The consequence copy has one source now.** `PRIVACY_OPTIONS` lives beside
  `LeaguePrivacy` in `lib/leagues.ts` and drives both create and settings; the shorter
  `PRIVACY_LABELS` used by league lists did not change.
- **Settings has no privacy fallback.** Its state is null until the league response seeds
  it, and the form stays unavailable until then, so a private or request league cannot
  transiently submit `public_open`.
- **The warning reuses the existing admin request read.** Settings queries the same
  `/join-requests` endpoint and React Query key as the request-management page; a
  consequential transition fails closed until that query succeeds.
- **Only real side effects confirm.** `public_request` → `public_open` names the pending
  count it will auto-approve; a changed value → `private` names the count it will cancel.
  Declining either confirmation prevents the PATCH.
- **The first targeted run exposed a browser-global shadow.** The page's slate-window state
  is named `window`, so the new call reached that object instead of browser confirmation;
  addressing `globalThis.window.confirm` fixed both failing tests, and 51 targeted tests,
  lint and typecheck then passed.
- **The first full gate run had one environment failure.** macOS `initdb` rejected the
  inherited `C.UTF-8` locale while every other completed check passed. The unchanged full
  gate reran with `LANG`/`LC_ALL=en_US.UTF-8` and all 11 checks passed.

**Next:** Batch 95 is still the first unchecked batch and remains soft-blocked. The next
executable group is Group J, Batch 104, followed by its explicit `/ship-prod` checkpoint.

## Batch 104 — Railway is retiring the config file three of our invariants are written in
**Commits:** 9bd62a6 · verified: `scripts/ci-local.sh` PASS (11 checks, green first run)

### Key facts for future sessions
- **The generated migration was not safe to accept.** Railway's dry-run converter emitted
  duplicate replica keys and omitted build, health, sleep, egress and restart settings, so
  the replacement was hand-authored from the old contract and checked as an evaluated graph.
- **The graph is deliberately narrow and fail-closed.** It owns only the existing `api`
  service, accepts only the recorded staging/production project-environment pairs and
  preserves every documented sealed variable name without exposing a value.
- **All three load-bearing couplings moved together.** The deployment-config gate evaluates
  `.railway/railway.ts`; `DEPLOY_REPLICA_COUNT=1` still enters the image; and the migration
  guard test proves a divergent declaration fails, including multi-region totals.
- **Ship owns the external apply.** Both exact targets produced read-only plans with zero
  additions or destroys. The ship workflows now require Node 22 for IaC, review/apply a
  pinned non-destructive plan, serialize any config deployment, then upload source.
- **Nothing was deployed in the batch run.** Group J stops here with production drift
  expected until an explicit `/ship-prod`, after which the deployed replica, region, sleep,
  IPv6 and readiness manifest must be checked before Group J can complete.

**Next:** Run `/ship-prod` for Batch 104, then rerun `/group-start J` so it can verify drift
is clear and mark the group complete. Batch 95 remains soft-blocked; Group K follows.

## Batch 105 — Coupon is one current-round job presented as two competing screens
**Commits:** f833776 · verified: `scripts/ci-local.sh` PASS (11 checks, green first run; rerun
green after the header change) · production-preview `coupon-flow` e2e PASS, screenshots in
`artifacts/batch-105/`

### Key facts for future sessions
- **`roundPhase` is the surface's spine, and its order is the product rule.** Settlement
  outranks everything; a *complete* coupon outranks the deadline, because everybody being in
  is what makes it worth copying and that routinely happens before the lock; only then can a
  round be `locked_incomplete`. `couponLeads` turns that into the page order.
- **`#coupon` is the canonical copy-section address** — `COUPON_SECTION_ID` /
  `couponSectionPath` in `lib/leagues.ts`. `/predictions/coupon` redirects into it carrying
  `?gw=`, and an incoming fragment beats the default. Batch 107's notification should mint
  its link with that helper, not by hand.
- **`leagueSwitchPath` deliberately still maps `/coupon` to `/coupon`.** Normalising it to
  the canonical path looked tidier and was worse: the legacy path redirects onward *with the
  section*, so switching league from it keeps the reader on the coupon rather than dropping
  them at the top of the round. Two existing tests state this.
- **The merged page reads two endpoints and guards the second.** `entriesForRound` merges
  coupon legs with the slate's absentees, and the coupon is the authority on anyone in both —
  a lagging slate must never demote a leg to "yet to pick". A response without an array
  `legs` is treated as no coupon, which is what made a stubbed `{}` render instead of throw.
- **A row with no selection now leads with the person.** The first cut kept the coupon
  hierarchy for every row, so a member who had picked nothing was drawn anonymously — the
  list named them nowhere. Caught by the incomplete-coupon test, not by types.
- **Two phase words were printed twice** — the status chip and the section heading both said
  "Coupon complete". The chip owns the round's state; the heading only names the section
  (`The coupon` / `Result`). `RoundStatus` also uses `Pick required` where `GameweekNav`'s
  badge says `Open`, so the two controls never repeat one word.
- **The e2e needs `FRONTEND_ORIGIN=http://127.0.0.1:4173`.** CORS is a single exact origin,
  so without it every sign-in fails at the `OPTIONS` preflight with a 400 and the flow looks
  like a login bug. Unrelated to this batch; it will bite the next browser run too.

**Next:** Batch 106 — home mixes the next round's clock with the previous round's odds. It is
the second half of Group K, web-only, and no `/ship-prod` is owed by either.

## Batch 106 — Home mixes the next round's clock with the previous round's odds
**Commits:** 5ac2b96 · verified: `scripts/ci-local.sh` PASS (11 checks, green first run) ·
production-preview `coupon-flow` e2e PASS, screenshots in `artifacts/batch-106/`

### Key facts for future sessions
- **`homeCardState` decides what the card may say, and the precedence is the product rule.**
  `settled` and `notOpenYet` both mean `between_rounds` *even when the member holds a pick* —
  that is the Sunday shape the batch was written for, and it is why last round's pick is no
  longer allowed anywhere near the `Next opens` clock.
- **`LastResultPanel` is now the only home for a settled round's pick, fold and price**, so
  it gained a fallback: with no `last_result` in the response it is built from a settled
  `current_round`. Without that, an API predating Batch 79 would show a settled round
  nothing at all once the primary card stopped carrying it. `current_round` cannot say how
  many legs landed, so that clause is omitted rather than guessed.
- **The fold is deliberately absent while picks are open.** It moves on every claim and was
  competing with the deadline; `showsCouponFigures` allows it only in `round_in_progress`,
  where the coupon is frozen. Progress (`n of m picked`) took its place, from that league's
  own `member_count`.
- **The hero glows stopped being filtered children.** They are radial gradients on one
  clipped layer, because a `filter` gives a child its own rendering context and WebKit
  paints such a child past a rounded parent's corners — the actual Safari defect. A
  background cannot escape `border-radius` in any engine, so the fix does not depend on the
  clip working; `overflow-hidden` and a matching `clip-path` stay as second and third lines.
- **WebKit could not be driven on this machine.** `playwright install webkit` refuses on
  macOS 13 ("does not support webkit on mac13"), and Safari itself needs `safaridriver
  --enable`, which needs the owner's password. The corners were verified in Chromium in
  both themes at 390×844 and by cropping the screenshots; the engine-specific risk was
  removed rather than tested around. **An owner glance at both hero corners in real Safari
  is still worth one minute.**
- **Home copy no longer claims a week.** "one clear view of every round", "No pick made this
  round" — a league sets its own window and several do not share one.

**Next:** Group K is complete, both batches web-only with no `/ship-prod` owed. The next
executable group is **L**: Batch 107 (API/data), then a mandatory `/ship-prod` checkpoint
before Batch 108. Batch 95 remains soft-blocked.

## Batch 107 — Pick notifications do not say how close the league is to a complete coupon
**Commits:** aeda5df · verified: `scripts/ci-local.sh` PASS (11 checks, green first run)

### Key facts for future sessions
- **The denominator counts members, not recipients, and that is the whole trap.** The query
  that finds recipients already existed and returning its length would have looked right —
  it would have announced a smaller league and called a round complete with muted members
  yet to play. `round_progress` deliberately does *not* filter on `notification_muted`;
  `notification_targets` still does. A pick left by someone who has since left or been
  deactivated is out of both halves, so `X` can never exceed `Y`.
- **The completion row exists for two independent reasons.** Two members claiming the last
  two selections seconds apart both commit and both then read `12/12`, so "did I complete
  it?" has no answer in application code — `uq_gameweek_completions_gameweek` decides it and
  the insert that lands is the transition. Separately, `delivered_at` stays null until a
  fan-out finishes, so a failed delivery is retried by the next submission on that round
  rather than lost. Either reason alone would justify the table.
- **`claim_pending_completion` uses `SKIP LOCKED`, not `FOR UPDATE`.** A concurrent
  submitter that queued behind the lock would wait out somebody else's webpush round-trips
  before its own pick response returned, then find the work done and skip anyway.
- **The router now has three post-commit transactions, not one.** Record, deliver, then the
  ordinary alert — each committing alone. One `try` around all three would tie the durable
  record to the outcome of a webpush call, which is the exact coupling the row breaks.
- **The completion replaces the ordinary alert; a change afterwards does not.** `completed_now`
  comes from the insert, so only the transition suppresses the ordinary push. A pick moved
  into an already-full coupon is ordinary, at `12/12`, and mints no second event.
- **Batch 76's copy assertions were rewritten, on purpose.** Three tests pinned
  `Dave took Arsenal to win at 1.80 in 2-1 Hibs.` and a title that differed between claim and
  move. The batch respecifies that line, so they now pin
  `2-1 Hibs` / `Dave picked Arsenal to win @ 1.80 · 3/12 picked` and assert the titles now
  match — the verb is the only thing left telling the two events apart.
- **`POST /picks` returns `SubmitPickResponse`, a subclass.** `GET .../pick` keeps the plain
  `PickResponse`: it answers "what did I pick", and an aggregate over the whole league has no
  business on a read that runs on every screen showing a member their own selection. The
  frontend types are structural, so nothing in `apps/web` needed touching — Batch 108 adds
  them to `types.ts` when it consumes them.

**Next:** Group L stops here. Batch 107 is API/data only and **is not live until `/ship-prod`**
— Batch 108 consumes `picked_count` / `member_count` / `all_picked` from the pick response and
must not reach Vercel before Railway serves them. Run `/ship-prod`, then rerun `/group-start L`
so it can verify drift and continue with Batch 108. Batch 95 remains soft-blocked.

## Batch 108 — Notification UI promises events the product does not send
**Commits:** 79b354b · verified: `scripts/ci-local.sh` PASS (11 checks, green first run)

### Key facts for future sessions
- **`all_picked` alone is not "you completed the round", and that is the batch's one real
  trap.** The API returns it true to *anyone* submitting into a full coupon, including a
  member changing their mind afterwards — Batch 107 arbitrates the real transition with an
  insert, but does not return the answer. The client settles it without a new API field
  because **a change of pick cannot fill a coupon**: it moves no count. So the rule is
  `all_picked && !heldPickBeforeSubmitting`, and adding a field would have cost another
  `/ship-prod`.
- **`holdsPick` is captured in `send()`, not read in `onSuccess`.** By then the hook's own
  `invalidate()` may have refetched the slate, and the answer would be the post-submission
  one — always "yes", which would switch the hand-off off permanently. Same ref-at-call-time
  shape as `mutateRef`/`reconcileRef` above it.
- **The completion replaces the "Grabbed …" toast** rather than stacking on it, mirroring
  the rule Batch 107 gave the push. One event reaches the member, and it is the one saying
  something they could not otherwise know.
- **A notice, not a toast, and it is not a style call.** Every other submission outcome is
  news; this one is a job. `OutstandingPickNotice` is the same argument about a different
  state, and the two now bracket the pick path.
- **`focusCouponSection()` is shared by the hash effect and the hand-off**, because a member
  who arrived from a notification is *already* at `#coupon` — an unchanged hash fires no
  effect, so the button focuses directly as well as navigating.
- **The opt-in list has five entries, not the row's four.** `fixture_postponed` is a real,
  member-facing, league-scoped push that hands somebody their claim back, and it predates
  the notification review the row was written from. A list whose entire purpose is
  truthfulness could not omit it. Flagged to the owner rather than slipped in.
- **The Settings rename is a safety fix, not wording.** "Per-league reminders" named one of
  the five things that switch silences; a member muting a league to stop being nagged was
  also switching off the alert that their pick had been returned.
- **Competitions start collapsed**, so every test that claims a selection is two clicks —
  open the competition section, then hit `selection-{fixture}-{market}-{outcome}`.

**Next:** **Group L is complete.** Batch 108 is web-only and reached members on this
close-out push; Batch 107's API has been live since the 2026-09-04 `/ship-prod`, so the
fields it consumes are served and no shipment is owed. The next executable group is **M**:
Batch 109 (web), Batch 110 (API/data), a mandatory `/ship-prod`, then Batch 111. Batch 95
remains soft-blocked.

## Batch 109 — Football results are a long archive when the task is moving through matchdays
**Commits:** e1ea13b · verified: `scripts/ci-local.sh` PASS (11 checks, green first run), plus a
browser pass at 390×844 in both themes against a stubbed season of 79 result days

### Key facts for future sessions
- **`scroll-behavior: smooth` and `scroll-snap-type: mandatory` together refuse a long
  programmatic scroll, and that is the one thing here the unit tests could never have
  caught.** Measured in Chrome on a full season: arriving on the newest day, with its chip
  8,443px along an 8,486px strip, `scrollIntoView` left `scrollLeft` at 404 and never moved
  — the heading read May while the strip showed the previous August. Short hops worked, so
  it would have shipped clean and only appeared once the archive filled. The strip carries
  no `scroll-smooth` and the call passes `behavior: 'instant'`; a test pins the option
  because jsdom has no `scrollIntoView` to catch the real thing.
- **The day key is derived in the member's timezone, not sliced off the ISO string.** A
  Friday 20:45 kickoff in Britain is Saturday morning in Auckland, so a slice would put
  `?date=` on a day the reader's own screen does not show.
- **This selection pushes history where `useGameweekHistory` replaces it.** `gw` is a filter
  on a screen; the day *is* the screen, so back has to be the way out of the archive. Both
  the newest day and the older ones write `?date=` explicitly — leaving the newest bare
  would mean a shared link silently moves to a different Saturday next week.
- **An unresolvable `?date=` renders the latest day and leaves the URL alone.** Rewriting it
  during render would spend a history entry undoing the member's own back button.
- **The strip is a `role="toolbar"` with roving tabindex**, so a season of Saturdays costs
  one tab stop rather than seventy-nine; that trade is only honest because the arrow keys,
  Home and End work and carry focus with the selection. Selected chips use
  `aria-current="date"` — the token means exactly this.
- **Two old assertions were rewritten, not weakened.** `lists previous results grouped by
  day, newest day first` asserted the shape this batch replaces, and the day heading gained
  its year (`Saturday 2 May` → `Saturday 2 May 2026`) because the abbreviated chips are the
  only other place the date appears and none of them name a season.

**Next:** Batch 109 is web-only and reached members on this close-out push. Group M continues
with **Batch 110** (API/data — provider-neutral match retention and the team-season read
contract), then a **mandatory `/ship-prod`** before Batch 111. Batch 95 remains soft-blocked.

## Batch 110 — The football store cannot answer a team's complete selected season
**Commits:** 3887a5a · verified: `scripts/ci-local.sh` PASS (11 checks; three failures on the
first run, all this batch's own, fixed and rerun green — see below)

### Key facts for future sessions
- **The date window on the daily sweep never saved a single upstream request, and that is
  why it could be dropped.** FotMob returns the whole season in the payload the league
  table already paid for, so `since`/`until` were client-side filters deciding how much of
  what had *already arrived* got written down. `fetch_season_matches` takes all of it. A
  provider that pages results — api-football — answers that method with `[]` and keeps the
  window it was tuned for, which is the pattern `fetch_fixture_states` and
  `fetch_live_scores` already established in this port.
- **`finished` is now derived from `state` where it is persisted, not trusted from the
  caller.** `MatchResult` reconciles the two in a validator, but `model_copy(update=...)`
  does not re-run validators — a test caught exactly that, writing `state='finished'` with
  `finished=false`. `sync_results` reads `state` and nothing else.
- **The two fields still part company in one real case, on purpose.** A match the provider
  calls finished but publishes no readable score for stays `state='finished',
  finished=false`: visible on a season, absent from the results screen and the form line,
  both of which mean "there is a scoreline here" by `finished`.
- **FotMob's `cancelled` flag is raised for postponements far more often than for
  cancellations**, and only `reason.longKey` separates them. Collapsing them would tell a
  member "that is the season" about a game being replayed on a Tuesday.
- **Three reads walked `allMatches` with the same twenty lines of division attribution**
  before this batch; a fourth copy is where one of them quietly stops agreeing with the
  others about which division a club is in. They now share `_parsed_matches`, and a test
  pins that a composite id (`8944` = National League North *and* South) still hands each
  division only its own season.
- **The daily sweep is now the backfill, for FotMob.** `backfill_season` still matters for
  a paging provider and the respecified
  `test_the_backfill_reaches_matches_the_daily_window_cannot` asserts both halves rather
  than dropping the old claim. What did change is write volume: every sweep upserts a full
  season per competition instead of a few days.

**Gate failures on the first run, all three this batch's own:** the `finished`/`state`
disagreement above; `test_the_window_counts_days_with_results_not_calendar_days` comparing
`recent_results` against *every* stored match, which now includes unplayed ones; and
`test_the_backfill_reaches_matches_the_daily_window_cannot` asserting a window that no
longer bounds a season-capable provider. The first was a code fix, the other two were
respecified with their original claims kept for the paging path.

**Next:** **Group M stops here.** Batch 110 is API/data only and **is not live until
`/ship-prod`** — Batch 111 makes league-table teams open
`/football/teams/:teamId?competition=…&season=…`, and that route 404s against the deployed
image until Railway moves. Run `/ship-prod`, then rerun `/group-start M` so it can verify
drift and continue with Batch 111. Batch 95 remains soft-blocked.

## Batch 111 — League-table teams are labels when they should open the season story
**Commits:** 0c1fd59 · verified: `scripts/ci-local.sh` PASS (11 checks; one failure, an unused
import of this batch's own, fixed and rerun green), plus a browser pass at 390×844 in both
themes against a stubbed 30-match season

### Key facts for future sessions
- **Putting the expanded division in the URL is what restores scroll, and that is the whole
  mechanism.** React Router v6/v7 without a data router manages no scroll at all, and the
  browser's native restoration only lands correctly if the page comes back the same height —
  which it cannot when every table defaults to collapsed. `?competition=` reopens the
  division, the height matches, and the browser does the rest. Measured: back returned to
  `scrollY: 465` of a 1309px page with the same 20 rows on screen.
- **The two query parameters are `replace`d while the results carousel `push`es.** Expanding
  a table is a filter on the screen; moving between matchdays *is* the screen. Getting that
  backwards would make the back button close an accordion instead of leaving Football Stats.
- **"Next" skips a postponed match.** A postponed fixture keeps its original kick-off, so it
  sorts into the fixture list on a night nothing is happening; highlighting it would point a
  member at that night. A cancelled one is never next. The rule is "earliest match that is
  `live` or `scheduled`", and a live one wins because it is happening now.
- **The club link needed `min-h-6`, which the browser found and jsdom could not.** A bare
  line of text renders a 164×20 box — four pixels under WCAG 2.2 SC 2.5.8, the identical
  shortfall Batch 55 fixed on the form disclosure. A standalone control in a table cell does
  not get the standard's inline-link exception. A test now pins the class.
- **The competition is named once in the header, not on every row.** The row asks for it on
  each, but the response is scoped to one competition by construction, so repeating it down
  the list is exactly the repetition Batch 105 was written to remove. Flagged rather than
  slipped in.
- **Batch 53's form disclosure is gone from the table, deliberately.** Its five matches were
  a hidden subset of the season the club's name now opens, and two ways into one thing — one
  of them invisible — is what the row exists to end. `FormLine` keeps its `onToggle` for the
  pick screen, which is a different surface and out of this batch's scope.

**Next:** **Group M is complete, and with it the 2026-09-03 review wave.** Batch 111 is
web-only and reached members on this close-out push; Batch 110's API has been live since the
2026-09-04 `/ship-prod`, so the route it consumes is served and no shipment is owed.
`docs/BUILD_PLAN.md` now carries **only Batch 95** unchecked, in the soft-blocked tail of
Group D — still waiting on the FEAT-A09 egress attribution and the off-platform-storage
decision.

## Batch 114 — The card offers prices that do not exist, and asking spends the quota
**Commits:** cc86312 · verified: `scripts/ci-local.sh` 11/11 green (second run; see below)

### Key facts for future sessions
- **The guard for this existed and was green throughout, because it declared its own
  premise.** `test_request_budget.py` asserted the whole arithmetic against a real
  `CachingOddsProvider` and claimed in its docstring that if it passed, real traffic could
  not exhaust the quota. It passed because `LAUNCH_SATURDAY_FIXTURES = 131` was hardcoded
  and the round production held was 202. Set it to 202 and exactly five tests fail — the
  saturated day, both ad-hoc round limits, one member changing their mind, and a league's
  whole pick allowance — while `test_saturated_browsing_near_lock_stays_inside_the_hourly_limit`
  still passes, which is why this arrived as a burst on a match morning rather than as a
  drift anyone could watch. The module now drives the real `askable`/`record_observations`
  loop and a Postgres-backed test fails when a live card outgrows the measurement.
- **`observed` is the field that makes the marker safe, and the port's default needed it
  too.** A degraded sweep, a cache hit and a browse withheld for the pick reserve must all
  be unable to conclude that a fixture is unpriced — otherwise a briefly unreachable
  provider blanks the card. `OddsSnapshot.observed` carries only the events that got a
  definite answer. The abstract `fetch_odds_best_effort` on `OddsProvider` returned an empty
  one, so an *unwrapped* provider could never teach the deployment anything; caught by a
  test, since production always hands out the cached provider.
- **The negative ceiling deliberately beats a tightened `max_age_seconds`.** The pick path
  asking again inside a minute cannot discover a market that is not there, so `_stale` uses
  `max(ttl, unpriced_ttl)` for a `None` entry. The bounded re-check, not a tighter ceiling,
  is what finds a market a bookmaker opens late.
- **A fixture somebody has claimed is never filtered off the card.** Not in the batch's own
  verification list, added because a bookmaker withdrawing a market hours after a claim
  would otherwise take a member's own selection off the screen they made it on. The pooled
  `fixtures` row is shared by every league, which is also why the HTTP tests mark through a
  fixture that takes the marker back in teardown.
- **`PRICE_MOVED` carries its value in the detail string.** `ApiError` keeps only a string
  `detail` (`lib/api.ts` drops a non-string one), and the member's decision is whether to
  take the new price, so the code alone is not an answer. `PRICE_MOVED:<price>` is the only
  detail in the API shaped that way.
- **Both web-half changes degrade against the un-shipped API.** `SubmitPickBody.odds` is an
  extra field pydantic ignores, and `AdminDashboard.odds_budget` is optional and its section
  simply does not render — so the Vercel deploy from this close-out is safe ahead of
  `/ship-prod`, which is not the usual case and was checked rather than assumed.

**Next:** **`/ship-prod` is owed and this one matters** — Batch 114 is a live production
defect fix whose API half is the fix. After it ships, delete `ODDS_CACHE_NEAR_TTL_SECONDS`
and `ODDS_CACHE_PICK_TTL_SECONDS` from the Railway `api` service (set by hand at 09:02 UTC
on 2026-09-05, absent from the repository) and confirm the `config.py` defaults hold. Then
Batches 112 and 113, in that order, per their own scope boundaries. Batch 95 is still
soft-blocked.

## Batch 119 — Discovery cannot afford to run, and nothing said so for a week
**Commits:** f69b5fe · verified: `scripts/ci-local.sh` PASS (11 checks)

### Key facts for future sessions
- **The catalogue measured 67 again on 2026-09-12**, a day after the row recorded it, so the
  number did not move — but `MEASURED_UK_CATALOGUE` / `MEASURED_PLAYED_CATALOGUE` (41) /
  `MEASURED_DAILY_WALK` (20) live in `services/competitions.py` with that date against them,
  and `test_the_daily_walk_is_no_bigger_than_the_database_says` reads the pool back out of
  PostgreSQL. Re-measure with `fetch_competitions`, not from a paragraph.
- **The trim rules land exactly on the owner's numbers.** Run against the live catalogue and
  the live pool: 67 → 41 played, and of the 33 competitions that had ever carried a fixture
  it removes precisely the 13 named (11 `england-amateur-*` including the FA Trophy, plus
  both Northern Ireland divisions) and keeps 20. The row's prose says "eleven English amateur
  divisions ... plus the FA Trophy", which double-counts; the arithmetic 13/20 is right.
- **`REQUESTS_PER_SLATE_WALK` was a third copy of the same stale 30**, in `admin_ops`. It now
  derives from the measurement. Making it honest turned the ad-hoc budget test red, and the
  fix was to narrow the ad-hoc walk the same way the daily one is narrowed — *not* to lower
  the shipped `2/hour;3/day` limit. An unconfigured league's ad-hoc fetch now costs ~20
  rather than 67.
- **The weekly full walk covers one window, rotated by ISO week**, not all of them. The
  fixture pool is deployment-wide, so a competition discovered through any window is one the
  daily run walks for every window from the next morning. Covering every window in one night
  is paying twice for the same lesson — and it is what put the worst-case day over 500.
- **Chunking moved from `OddsApiProvider._event_odds` into `CachingOddsProvider._refill`.**
  It had to: `observed` is computed in the cache, and marking a whole refused chunk unpriced
  would hide nine pickable fixtures to record one dead one. The provider still chunks for a
  direct caller. `odds_calls` in the cache tests now counts *requests*, which is what the
  plan bills — the old `len(odds_calls) == 1` was counting a call that was never the billed
  unit.
- **The Batch 114 observability gap was accepted deliberately, not fixed.** A fixture that
  was priced and still is writes nothing, so "never swept" and "swept, everything priced"
  stay indistinguishable. Resolving it wants a sweep timestamp per round, which wants a
  column, and this batch carries **no migration by design** — head stays `023`, which is what
  keeps a rollback available for the shipment it is sequenced before. Written down in
  `services/odds_warm.py` and asserted in `test_discovery_budget.py`.

**Next:** `/ship-prod`, then Batches 118 and 117.

## Batch 118 — Every word the product says to someone outside it describes a flow that no longer exists
**Commits:** a29662a · verified: `scripts/ci-local.sh` PASS (11 checks), first attempt

### Key facts for future sessions
- **An owner decision was taken rather than deferred, and it should be confirmed.** The row
  asks the owner whether desktop is a supported way to play or a prompt to install. Nobody
  was there to ask, so the majority reading was taken — `DesktopInstructions` said the app
  works in a desktop browser and `InstallPromptController` gated nothing off a phone, so the
  invite copy was the odd one out. Everything written for desktop follows from that: if the
  owner wants desktop treated as "install on your phone instead", the desktop card in
  `BrowserOnboarding` and one sentence of `buildInviteMessage` are what change.
- **`WelcomePage` is deleted and `/welcome` renders `BrowserOnboarding`.** The surviving name
  is now a misnomer — it is the landing surface on every platform, not a browser-only gate —
  but renaming it would have churned the controller, `JoinPage` and the test file the row
  names by name. Worth doing next time somebody is in here.
- **The cold-visit redirect is in `ProtectedRoute`, and its two exclusions are load-bearing.**
  Only `pathname === '/'`, and only when `!detectStandalone()`. A deep link is a returning
  member and still goes to `/login`, where `next` brings them back; an installed PWA with an
  expired session must not be told to install what it is already running inside.
- **Share picks an existing invite; it never mints one.** `handleShare` looks for a live,
  unused, unexpired invite in the list the page already holds and falls back to the join-code
  wording when there is none. Pressing Share must not create a credential as a side effect.
- **The message is capped under 400 characters and both variants are asserted.** With a link
  it is 379, without one 371 (test params). The linked variant collapses the fallback to a
  single `origin → Leagues → Join by code → CODE` line — the link above already names the
  league, so the separate `League:` line was spending 20 characters to repeat it.
- **The invite tests now assert claims, not strings.** The old suite pinned `display name and
  PIN` and `your admin` and stayed green for three weeks while the flow it described was gone.

**Next:** `/ship-prod` (Batch 119's API half is owed), then Batch 117.

## Batch 117 — Home names the round it has finished with, and the coupon is last on the coupon page
**Commits:** bf87f0a · verified: `scripts/ci-local.sh` PASS (11 checks), first attempt

### Key facts for future sessions
- **A second owner decision was taken rather than deferred.** The row asks what a deep link
  should do to a collapsed section and calls auto-expanding "the obvious answer"; nobody was
  there to confirm it, so it was taken. All three ways into the section — the completion
  notice, the `#coupon` fragment a push notification carries, and `focusCouponSection` — now
  open it. The cost is that the open state is not purely the member's, and it is one line in
  each of the three call sites if the owner wants it back.
- **`CurrentRound.number` is optional *and* nullable on the web side, and the two are
  different facts.** `null` is a round discovered before Batch 41; *absent* is the window
  between this close-out and its `/ship-prod`, which is live right now. `roundName` prints
  the date for both, and `DashboardPage.test.tsx` tests the absent case explicitly by leaving
  `number` off `work-league`'s fixture.
- **The fold is the legs, not the whole section.** The fold count, the frozen price and the
  copy control stay visible when it is closed — they are fixed-height, and they are what
  makes leading with the section worth doing at all. What folds is the one row per member,
  which is the part that would have pushed the slate down by the league's membership.
- **The open state lives on the page, not in `CouponSection`.** Three things outside the
  component open it on arrival, and a page-level `useState` also survives the once-a-second
  re-render the lock countdown causes. `CurrentRoundPage.test.tsx` asserts that by waiting
  for the clock text to change rather than by simulating a render.
- **`couponLeads` is deleted.** With the coupon always leading it had no callers; its tests
  went with it rather than being left asserting a rule nothing consults.
- **This batch is why a `/ship-prod` matters twice over.** The web half is live from this
  push and prints dates where it will print "Gameweek 6" once the API ships `number`.

**Next:** `/ship-prod` — Batch 119's API half and Batch 117's `number` are both owed. Then
Batch 116 (migration `024`, merged but not shipped).

## Batch 116 — A pick alert names a selection nobody can place (item 1 only)
**Commits:** b7afab2 · verified: `scripts/ci-local.sh` PASS (11 checks), **second attempt**

### Gate failures on the way
- **`ruff format --check`, first attempt.** `src/routers/picks.py` and the new
  `tests/test_alert_names_the_fixture_batch_116.py`. Reformatted with the pinned 0.5.4 and
  rerun green. No other check failed at any point in this batch.

### Key facts for future sessions
- **Item 2 is NOT built, and the row is deliberately left unchecked.** "The product's name
  arrives twice" is conditional on an owner decision the row calls blocking — *"a screenshot
  of the actual notification… Guessing here ships copy the owner did not ask for, into the
  one surface that reaches a phone unprompted."* Both candidates are choices rather than
  edits, and one of them (renaming `short_name` in `vite.config.ts`) would give this batch a
  web half it is scoped not to have. Striking the row would have hidden an unbuilt half.
- **Migration `024` is on `main` and production is at `023`.** Nothing in this batch is
  deployed. Its forward recovery plan is in `docs/launch/L4_PRODUCTION_INFRASTRUCTURE.md`
  marked *awaiting owner approval, not cleared to ship*, with production measured read-only
  on 2026-09-12: `gameweek_completions` holds **1 row**, no colliding columns, 0 undelivered
  completions.
- **Four columns, not one composed phrase, and that is the row's instruction.** Storing
  `Both teams score (Arsenal v Chelsea)` would work today and would make the next copy
  revision a migration. `selection` stays the frozen `runner_name` datum and is the fallback
  for any row written before `024` — there is nothing honest to backfill from, because the
  round may since have settled and the picker may since have moved.
- **The API's vocabulary and the web's had *drifted*, not merely diverged in coverage.** The
  API said `The Draw` where `lib/coupon.ts` says `Draw`, and `Yes` where it says `Both teams
  score`. `services/selection_text.py` is written to mirror `outcomeLabel` /
  `fixtureContext` / `selectionSummary` branch for branch, and
  `test_the_api_says_what_the_web_says` spells out all five branches so a change on either
  side has to change a test on this one.
- **`record_completion`'s four new parameters are required, not defaulted.** A default would
  let a caller silently drop the fixture and put the defect straight back; the seven test
  call sites were updated instead.
- **The new tests drive the submit endpoint, not `notify_pick_made`.** The defect was never
  in the notifier — it is handed a string, and the string was wrong. A unit test on the
  notifier would have passed throughout, which is why `test_notification_batch_76.py`'s
  assertion is left as it was with a note pointing at the endpoint-level test.

**Next:** the owner's screenshot for Batch 116 item 2, and the owner's approval of the `024`
recovery plan before any `/ship-prod` carries it. Then Batches 112, 113; 95 is soft-blocked.

## Batch 116 — A pick alert names a selection nobody can place (item 2)
**Commits:** 7967e4d · verified: `scripts/ci-local.sh` PASS (11 checks), first attempt

### Key facts for future sessions
- **Item 2 resolved to "no change", and that is the finding rather than a dodge.** The row
  named two candidates and refused to start without a screenshot. It arrived 2026-09-12 and
  showed every alert titled with the **league** — "2-1 Hibs" — under an OS line reading
  "from Coupon". The title was already right; the second line is the platform's attribution
  for an installed PWA, which `vite.config.ts`'s `short_name` names and which cannot be
  suppressed, only renamed. The owner chose to leave it. So there was never a duplication on
  the route the owner was actually looking at.
- **The row's other candidate is real, unreachable, and now asserted rather than fixed.** A
  league whose own name is "The Coupon" would be titled that beneath a header reading
  "Coupon". No live league can produce it — `the-coupon` is soft-deleted and the two live
  leagues are 2-1 Hibs and McCann's Defenders — and closing it means choosing what such a
  league's alert should say instead, which is copy reaching a phone unprompted. Asserted as
  a known gap in the style Batch 89 used for the unbounded pick path; the test is what a
  future session deletes when somebody decides the rule.
- **The manifest is pinned from a Python test, deliberately.** The duplication is a property
  of a *pair* — the title is composed in `notification_triggers.py` and the attribution in
  `apps/web/vite.config.ts` — and neither file can see the other, which is why nobody caught
  it. `test_the_tray_attribution_is_the_name_this_module_assumes` reads the manifest so a
  rename has to come back through the reasoning that depends on it.
- **The screenshot independently confirmed three other things.** Item 1's defect is live in
  production ("picked Yes @ 1.57", no fixture) and is fixed by the half already merged;
  2-1 Hibs's hand-built round opened on schedule at 03:01 via `run_open_gameweeks`, behaving
  like any other round rather than a special case; and Batch 107's progress counts are
  correct, including a re-pick not incrementing the numerator.

**Next:** **`/ship-prod` is owed and now carries migration `024`.** Its forward recovery
plan is written and still marked *awaiting owner approval*; approving it is the gate. That
ship also carries Batch 117's `number`, so home stops printing dates and starts printing
"Gameweek 6" at the same moment. Remaining unchecked: Batches 95, 112, 113 and 115.

## Batch 112 — A window change strands the rounds built against the old one
**Commits:** 282db2a · verified: `scripts/ci-local.sh` PASS (11 checks), **second attempt**

### Key facts for future sessions
- **The retirement rule is bounded to the horizon, and that bound is the whole design.**
  Without `starts_on >= today` every past round nobody happened to pick on matches the rule
  — a legitimate Saturday the league forgot is not junk — and retirement would quietly eat
  the season. The cost is that a stranded round already in the past survives as an inert
  row; it is off the discovery horizon by the same bound so it is never re-synced, and its
  effect on `current_round_order` expires with `IN_PLAY_GRACE_MINUTES`. Changing that
  ordering is explicitly not this batch's.
- **Order matters in `discover_fixtures`: retire *before* `unlocked_round_dates`.** That
  read is what put a stranded round back inside the horizon every morning, so retiring
  after it would delete a round and re-feed its date in the same run.
- **The already-locked refusal is conditioned on `status is None`.** It only ever declines
  to *create*. A league mid-season holding a round on today whose lock passed this morning
  is a real week, and an unconditional rule would have dropped it on the next rebuild.
- **Two gate failures, both the batch's own doing, both narrowed rather than deleted.**
  `test_discovery_refreshes_an_unlocked_round_off_the_cadence` and
  `test_two_leagues_sharing_an_off_cadence_date_share_one_fetch` asserted that an *unclaimed*
  off-cadence round survives to be refreshed, which is exactly what this batch stops. The
  property survives with a narrower precondition — a round holding a claim — so both now
  add a pick via a new `_claim` helper. The third failure was the web test for the removed
  card, replaced by an assertion that the card and its input are gone.
- **`PROVIDER_SLATE_FETCH_LIMIT` outlived the endpoint that named it.** Two spenders remain:
  `refresh_rounds` on a cadence date the pool cannot serve, and the admin console's sync
  trigger. `test_request_budget.py`'s ad-hoc section is renamed to match — the assertions are
  unchanged, the prose described a route that no longer exists.
- **`refresh_slate`'s docstring claimed the ad-hoc endpoint as its only production caller.**
  It is now `populate_cadence_rounds`, reached only for a cadence date the pool cannot
  serve — the same unshared-fetch case, so the reasoning it gives is still right.

**Next:** **`/ship-prod` before Batch 113**, which the rows require of each other: 112's
scope boundary says stop for a ship, and 113 says do not begin until 112 has shipped and
`check-deploy-drift.sh` reports in sync — 113 replaces the endpoint 112 removed, so it
assumes 112's API is live. That ship also carries migration `024` (Batch 116), whose
recovery plan still awaits approval.

## Batch 113 — The deployment has no season calendar, so every league counts alone
**Commits:** `f748117` · verified: `scripts/ci-local.sh` PASS (11 checks); production-preview
Playwright coupon flow PASS against disposable PostgreSQL through migration `025`, with
390x844 light/dark screenshots and `Gameweek 1b` inside the viewport

### Gate failures on the way
- **First full gate:** pinned mypy rejected two implicit re-exports after `season_bounds`
  and `season_label` moved to the calendar module; both callers now import the canonical
  module directly. PostgreSQL also failed before migration because the inherited `C.UTF-8`
  locale is not installed; reruns used the installed `en_US.UTF-8`. The locale reset did not
  count as a code attempt.
- **Next full gate:** Ruff caught the import ordering introduced by that fix; the import was
  reordered. Six football-data tests then failed because the new admin HTTP test committed a
  far-future fixture which their later shared-pool discovery correctly found. The test now
  removes only its own committed league, fixture, profile and calendar. The exact ordered
  slice passed 44/44 before the complete gate was rerun green. A run already collected before
  that edit repeated the same six failures; no production logic or expected value was changed.
- **Browser verification:** the first harness used `/health` instead of `/api/v1/health` and
  stopped before Playwright. The first real browser run reached the final legacy empty-league
  assertion as its 30-second overall budget expired under competing test load; the unchanged
  rerun passed. Visual inspection then showed the hash had scrolled the week label above the
  screenshot, so the acceptance test now requires it inside the viewport; the final unchanged
  journey passed again in both themes.

### Key facts for future sessions
- `season_calendars` is deliberately empty after migration `025`. The production backfill is
  not a migration or ship side effect: dry-run, owner review, explicit apply, then dry-run again.
- The stored anchor never follows a later-added earlier round. Earlier history clamps into week
  1 and is disambiguated by the same chronological suffix rule as a global extra date.
- Global extras are intent, not placeholder rounds. Scheduled discovery offers each date to all
  leagues once per distinct window; a competition-filtered empty slate creates no round.
- Withdrawing an extra is refused if any league has a pick on that date. Without picks, Batch
  112's cadence-union-extras retirement removes the now-stranded round.
- `Gameweek.number` and `next_gameweek_number` are untouched internal ordinals. Public API
  responses add optional `season_week`; every member-facing label prefers it and remains
  compatible while the deployed API lags the web push.
- The admin Calendar page reads the current season, moves only an unsettled anchor, declares
  extras globally, and makes the deferred discovery behavior explicit.

**Next:** `/ship-prod` for migration `025` and the additive calendar API, then the separately
authorised production calendar dry-run/apply. Batch 95 remains soft-blocked; Batch 115 remains
unchecked because Batch 119 superseded it.

## Batch 152 — The gate can pass without testing the bundle, and nothing notices a weakened gate
**Commits:** `5cefff3` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,172 backend and
1,045 frontend tests passed, 0 skipped; strict-port production-bundle Playwright smoke passed

### Key facts for future sessions
- Test counts are exact ratcheting baselines in `scripts/ci-test-counts.env`: a fall fails,
  an unrecorded rise fails with instructions to raise the baseline, and a baseline reduction
  is refused before the gate runs.
- Ordinary batches cannot change the gate, CI workflow, test discovery, package test command,
  or lint/type configuration. Batch 152's bootstrap exemption required its named branch and
  its source row to remain unchecked; a temporary ordinary branch refused the same diff.
- The production preview uses strict port 4173, waits for its own Vite readiness line plus an
  HTTP response, and shares one helper between local and GitHub gates. Holding the port with
  another server failed loudly before Playwright ran; the normal five-test smoke passed.
- Removing one frontend test for the rehearsal produced 1,044 against the recorded 1,045 and
  failed the full gate. The test was restored before the final 11-check run.
- Close-out now runs deployment drift before the push and classifies the batch diff. A
  temporary API+web diff was refused until an explicit shipment acknowledgement; tooling,
  web-only and API-only batches report their actual deployment consequence.
- The rehearsal's first full gate also found the inherited `C.UTF-8` unsupported by this Mac;
  `pgserver` passed under installed `en_US.UTF-8`. This was an environment reset, not a code
  fix. The final full gate passed first attempt with that locale.

**Next:** `/group-start N` (Batches 120 → 121 → 122), then its explicit `/ship-prod` checkpoint.

## Batch 120 — The member who loses a simultaneous claim is told the app failed, not that someone beat them to it
**Commits:** `c822e69` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,174 backend and
1,045 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- The conflict code is captured before commit because rollback expires the league object;
  the database uniqueness constraints and pre-check remain unchanged.
- The regression synchronises ten real HTTP requests after the pre-check in each claim
  scope. PostgreSQL chooses one winner; all nine losers receive the scope's 409 code and
  the configured CORS origin, with exactly one pick stored.
- The first gate run hit the known unsupported `C.UTF-8` locale before PostgreSQL started.
  This was an environment reset; the clean reruns used `en_US.UTF-8`.
- The first database-complete rerun passed 1,174 tests but the ratchet still recorded
  1,172. The baseline was raised by two as instructed, then the full 11-check gate passed.
- The close-out guard classified the batch API-only and found the deployed API in sync
  beforehand. This batch therefore joins the Group N `/ship-prod` owed after Batch 122.

**Next:** Batch 121, then Batch 122 and the explicit Group N `/ship-prod` checkpoint.

## Batch 121 — A round stranded by a window change can be picked, settles, and scores
**Commits:** `be387da` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,177 backend and
1,045 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- Retirement's far bound is now the Tuesday ending the final cadence date's football week.
  This closes the Saturday just beyond a new Friday cadence without widening into history.
- Discovery can pass extras preloaded only through its ordinary horizon, so retirement
  loads the short tail itself and cannot delete a declared date after that horizon.
- Settlement identifies the current cadence and declared global extras as intentional.
  An undeclared same-week duplicate is left pending and logged with both round ids.
- A declared extra beside the normal round remains scoreable as Batch 113 requires; the
  guard does not collapse intentional `b`/`c` rounds into one.
- Focused PostgreSQL verification passed 14/14 and the complete 11-check gate passed on
  its first run under the documented `en_US.UTF-8` locale; no gate failure needed a fix.
- The pre-push guard found Batch 120 already owed one API shipment and classified Batch
  121 API-only. Both stay queued for the single Group N `/ship-prod` after Batch 122.

**Next:** Batch 122, then the explicit Group N `/ship-prod` checkpoint.

## Batch 122 — A league admin can clear any member's PIN, including a site admin's, and take over the account
**Commits:** `30fe08b` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,179 backend and
1,045 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- The league-scoped reset refuses a target whose profile has the site-admin role or whose
  active membership makes them an admin of any league, not only the current league.
- Both privileged cases return `403 SITE_ADMIN_RESET_REQUIRED`; the shared response says
  where recovery belongs without revealing which privilege the target holds.
- The refusal happens before `clear_pin`, audit or commit, so the PIN and every live session
  remain intact and no unauthenticated 24-hour claim window opens.
- The site-console endpoint is deliberately unchanged and successfully resets the same
  protected target; the existing ordinary-member league reset also remains green.
- Focused PostgreSQL verification passed 18/18 and the complete 11-check gate passed on
  its first run under `en_US.UTF-8`; no gate failure needed a fix.
- The pre-push guard found Batches 120 and 121 already owed and classified Batch 122
  API-only. One explicit Group N `/ship-prod` now carries all three.

**Next:** `/ship-prod`, then rerun `/group-start N` to verify the checkpoint in sync.

## Batch 158 — Keyboard focus is invisible on every button in the app
**Commits:** `fa922f8` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,179 backend and
1,073 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- The fix is opacity, not hue. `--shadow-glow` is now `0 0 0 2px var(--surface), 0 0 0 5px
  var(--primary-ink)` — a gap layer then a solid ring — and the accent token mirrors it.
- Tying the ring to the `-ink` half of the brand token means the existing 4.5:1 assertions
  on ink tokens already guarantee the ring clears 3:1 in both palettes; it cannot drift.
- The gap layer is one colour for four surface tiers. That works only while the tiers stay
  within 1.24:1 of each other, which `contrast.test.ts` now asserts explicitly.
- `--shadow-glow-on-brand` exists because a control sitting on a `--primary` fill would lose
  both other layers into its own ground. The update banner's button is the only user.
- No component class string changed for the 49 existing `focus-visible:shadow-glow` sites,
  so `TeamSeasonPage.test.tsx`'s focus-ring assertion still holds unedited.
- A new test walks `src/components` and `src/pages` and fails on any `focus-visible:ring-`,
  which is how the two unmeasured hold-outs survived the original sweep.
- Gate green on the first run; the only change needed was raising FRONTEND_TEST_COUNT from
  1,045 to 1,073 for the 28 tests this batch adds.

**Next:** Batch 137.

## Batch 137 — Four more public screens still render outside the app shell
**Commits:** `8ed2740` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,179 backend and
1,083 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed (13 tests)

### Key facts for future sessions
- `CardTitle` now takes `as?: 'h1' | 'h2'`, default `'h2'`. It exists so a page rendering
  outside `Layout` can supply the document's `<h1>` without re-typing the class string, which
  Batch 86 had already done twice by hand.
- `BrowserOnboarding` takes `landmark?: boolean`. It is the page on `/welcome` and in
  `JoinPage`'s mobile branch, and a full-screen *overlay* from `InstallPromptController`
  everywhere else — where the route underneath already owns a `<main>`. Only the first two
  pass the flag, and a test asserts the default renders no `<main>` at all.
- The jsdom suite and the prod-bundle browser suite now both enumerate every public route.
  The split is still forced: `landmark-one-main` and `page-has-heading-one` resolve through
  axe's visibility check, which jsdom cannot satisfy, so only the browser run decides them.
- The prod-bundle a11y spec's readiness wait is per-route now; two of the six public routes
  have no `<form>` to wait for.
- Verified the new assertions are not vacuous: reverting `ForgotPinPage` alone turns both of
  its theme cases red, then green again on restore.
- Gate green on the first run; the only change needed was raising FRONTEND_TEST_COUNT from
  1,073 to 1,083.

**Next:** Batch 138.

## Batch 138 — A 70% opacity drops two AA-tuned surfaces below contrast
**Commits:** `6794111` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,179 backend and
1,096 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- The review's two measurements reproduce exactly from the tokens: kick-off time 2.83:1 light,
  "now" badge 3.58:1 light / 4.06:1 dark. The badge figure is the *unselected* chip.
- Bigger finding, not in the review: the **selected** chip fails without any opacity. Brand ink
  on `bg-primary/15` over a `bg-surface-elevated/70` panel is 3.87:1 light (season strip) and
  3.95:1 (results-day carousel, no panel). The chip label, not just the badge, was under AA.
- No brand-family token clears 4.5:1 on that tint in light — `--primary-dark` reaches only 4.32
  on the darkest ground — so a green-on-green chip cannot be fixed by picking a different green.
  Both chips use `--text-primary` and keep the brand cue in `border-primary/40 bg-primary/15`.
- `contrast.test.ts` now composites grounds (`over(fg, alpha, bg)`). Every earlier assertion in
  that file measured a token against a *surface tier*, and none of these three grounds is one —
  which is how this defect class keeps returning.
- The opacity guard allows `opacity-40` on the carousel's disabled step buttons: WCAG 1.4.3
  exempts inactive components. It refuses an opacity utility only on text that is still live.
- Not in this batch: UX-18's `opacity-60` payout figure on PickCard/PickRow (2.83:1 dark,
  2.38:1 light). The review says it is the same family; Batch 138's row does not cover it and
  no batch row currently does.
- Gate green on the first run; FRONTEND_TEST_COUNT 1,083 → 1,096.

**Next:** Batch 139.

## Batch 139 — The pick screen opens with every fixture hidden, and every outcome arrives as the same red toast
**Commits:** `7d0e56b` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,179 backend and
1,110 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `CompetitionSection` takes `defaultOpen`, passed only for `groups[0]`. It seeds `useState`
  and nothing else — a member who closes the first group keeps it closed across a refetch.
- `pickRefusal(detail)` is the new entry point and returns `{ tone, message, action?, price? }`.
  `pickErrorMessage` survives unchanged as the sentence half, so its nine copy tests are intact.
- `actionFor` maps a refusal to a sonner action button. `refresh-card` calls the hook's
  `invalidate`; `retake-price` re-sends the same body through `sendRef`, which exists because
  `onError` is declared above `send`.
- The lost-race toast deliberately does **not** auto-refetch. Doing it silently would move the
  card under the member's finger; the button lets them choose, and costs one request not two.
- The PRICE_MOVED copy is unchanged — it still ends "Tap again to take it", which is still
  true — so the button is additive and no copy expectation moved.
- Three existing tests changed with the behaviour, none weakened. Two ordering tests located a
  header by `{ expanded: false }` and now use position; the collapsed-by-default test asserts
  the new specified default and gained a companion proving the member can still close it; the
  coupon-completion helper now opens its group only when it is not already open (clicking an
  open header closed it, which read as the fixture vanishing).
- `vi.mock('sonner')` in usePickEditor.test.tsx now stubs `warning` and `info` as well.
- Gate green on the first run; FRONTEND_TEST_COUNT 1,096 → 1,110.

**Next:** Batch 167, the last of Phase 3.

## Batch 167 — Three keyboard and reflow defects the automated sweep cannot see
**Commits:** `597905d` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,179 backend and
1,122 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed (25 tests)

### Key facts for future sessions
- `Sheet` takes an optional `triggerRef` and handles `onCloseAutoFocus` itself. Radix restores
  focus to a `Dialog.Trigger`; this sheet has none, which is the whole cause — the account
  menu is a Radix dropdown *with* a trigger, which is why it was always correct.
- Sonner 1.7.4 has no per-toast `aria-live` and renders one `<section aria-live="polite">`
  around the stack, but it forwards a ref to that section. `AppToaster` sets `aria-live="off"`
  on it in an effect with no dependency array: React only writes an attribute when the
  rendered value changes, and sonner always renders "polite", so a remount would restore it.
- `AppToaster` reads the stack through sonner's exported `useSonner()` and mirrors titles into
  a `role="alert"` region and a `role="status"` region. Only string titles are mirrored.
- Warnings are assertive alongside errors: Batch 139 made a lost claim race a warning, and it
  is still a refusal the member has to answer.
- `e2e/prod-bundle-reflow.spec.ts` flags an element only when its overflow is hidden/clipped
  *and* its content exceeds the box — a scroll container is a design decision, not a defect.
  Verified non-vacuous by forcing a clipped `<h1>`: six routes went red, then green on revert.
- The review's "three further elements clip under the text-spacing override" are unnamed and
  were measured against a signed-in instance. The new sweep covers the six public routes and
  finds none there. The pick screen needs a session the prod-bundle harness has not got, so
  its label is held as a class contract in `PickCard.test.tsx` instead.
- Gate green on the first run; FRONTEND_TEST_COUNT 1,110 → 1,122.

**Next:** Phase 4 — `/group-start O` (123 → 124 → 125 → 126), then its `/ship-prod`.

## Batch 123 — A named member can be locked out of sign-in for a whole Saturday
**Commits:** `37c6e40` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,187 backend and
1,126 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- The lockout is untouched: five attempts, fifteen minutes, a correct PIN still refused
  during one. `test_brute_force_is_unchanged` asserts all three in one place.
- `refreshStoredSession` in `lib/api.ts` is deliberately *not* `silentRefresh`: it does not
  clear storage on failure, because the PIN screen is the fallback and it needs the stored
  player to render.
- `AuthState.sessionResuming` exists so `ProtectedRoute` shows "Resuming your session…"
  rather than a PIN prompt during the refresh — a flash of "enter your PIN" at a member who
  is about to be admitted without one is the defect in miniature.
- Unlock messages are mapped from the HTTP status through `UnlockRefused`, not sniffed out
  of `detail`. A terse API sentence must not replace one written for a member.
- `LOGIN_SOURCE_FAILURE_LIMIT` is charged through `login_failure_charger`, a dependency that
  returns a *callable*. It must run after the PIN check — as a plain dependency it would
  charge correct sign-ins and lock out a shared NAT — and it rides the limiter session, not
  the handler's, because the handler commits and then raises.
- The lockout push fires once per lock (`just_locked`), not per attempt, or griefing would
  become a push flood. It is wrapped so a dead subscription cannot turn a 401 into a 500.
- Gate failure, attempt 1: `test_the_source_budget_is_charged_by_a_wrong_pin` looked the
  counter up under `login-src:testclient`. Under `ASGITransport` the client address is
  `127.0.0.1`, so the row was never found — and the companion "a correct PIN spends nothing"
  test was passing vacuously for the same reason. Both now find the row by `login-src:%`
  prefix and assert a **delta**, since every test in that module shares one source address.
  Green on attempt 2. No product code changed to reach it.
- Counts: BACKEND 1,179 → 1,187, FRONTEND 1,122 → 1,126.

**Next:** Batch 124, then 125, 126, then the Group O `/ship-prod`.

## Batch 124 — A removed member walks back in with the old join code
**Commits:** `da8a13d` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,193 backend and
1,127 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- Rotation, not an exclusion list, was chosen from the two options the row offers. It needs
  no migration and it is the only mechanism that actually closes the door, because the code
  is readable by every member and the removed member has already seen it.
- `_create_join_request` is extracted into `routers/leagues.py` and imported by
  `league_memberships.py`, so `/join` and `/join-by-code` cannot answer a `public_request`
  league differently again. A test drives one door then the other and expects
  `JOIN_REQUEST_PENDING`.
- `JoinByCodeResponse.status` defaults to `"joined"`, so the field is additive.
- **Deviation from the row, deliberate:** the row says "API-carrying" and this batch also
  changes two web files. Shipping an API that can answer `pending` while the client
  navigates into the league on any 200 would strand a member inside a league they are not
  in. The web change is inert against an API that never sends `pending`.
- `test_league_join_gate.py` is new and Postgres-backed; it tags every profile and league
  because the HTTP endpoints commit through their own sessions.
- Gate failure, first attempt (in the focused run, before the gate): the new audit assertion
  used `AuditLog.league_id` / `AuditLog.action`, which do not exist — the columns are
  `target_table` / `target_id` / `action_type`. Fixed in the test; no product code moved.
  The full gate was then green on its first run.
- Counts: BACKEND 1,187 → 1,193, FRONTEND 1,126 → 1,127.

**Next:** Batch 125, then 126, then the Group O `/ship-prod`.

## Batch 125 — A site admin can consume a selection in a league they never joined
**Commits:** `623f9b7` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,200 backend and
1,127 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- Both `src/deps.py` and `src/routers/leagues.py` now carry a pair: `require_league_member`
  (bypass kept, reads) and `require_league_member_write` (no bypass at all). They already
  duplicated the read variant; the split follows the duplication rather than merging it.
- Exactly two mutating routes used the member dependency: `POST /{slug}/picks` and
  `PUT /{slug}/members/me/display-name`. Joining, claiming an invite and the admin console
  depend on neither variant and are untouched.
- **`app.routes` is not a flat list on fastapi 0.141.** `include_router` leaves
  `_IncludedRouter` wrappers that expose no `.routes` and reach their own only through
  `.original_router`. The obvious walk finds four OpenAPI routes and nothing else — the
  first version of the structural guard passed while asserting nothing, in both the fixed
  and the broken state. `test_the_route_walk_actually_finds_the_routes` exists so that
  cannot recur silently on a future upgrade.
- Both new assertions were verified against the defect: reverting `submit_pick` to the read
  variant turns the behavioural test *and* the structural guard red.
- Counts: BACKEND 1,193 → 1,200. Frontend unchanged.

**Next:** Batch 126, then the Group O `/ship-prod`.

## Batch 126 — A member can display another member's exact name on the league table
**Commits:** `ae187ea` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,208 backend and
1,127 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `src/display_name.py` now owns `MIN/MAX_DISPLAY_NAME_LENGTH`, `DISPLAY_NAME_RE`,
  `normalise_display_name` and `validated_display_name`. `routers/auth.py` keeps its old
  private names as aliases, so registration is byte-for-byte unchanged and nothing that
  imported them had to move.
- Uniqueness is on the **effective** name — `coalesce(display_name_override,
  profiles.display_name)` — because that is what every surface renders. Scoped to one
  league: two leagues are two games, so the same name is free in another.
- Clearing an override is deliberately *not* clash-checked. The fallback is the profile's
  own globally-unique name, and refusing the clear would trap a member holding an override
  written before this batch.
- Refusal is `409 NAME_TAKEN_IN_LEAGUE`. There is no web caller of this endpoint yet, so
  the batch is cleanly API-only.
- Three self-inflicted test failures on the way, all in the test and none in product code:
  a literal "Alice Smith" reused across tests violates the global unique index on
  `lower(display_name)`; `" leading-punct"` is *legal* because normalisation trims first;
  and an index-based emoji substitution silently pointed at the wrong list entry after I
  inserted two cases above it.
- Counts: BACKEND 1,200 → 1,208.

**Next:** the Group O `/ship-prod` checkpoint, carrying Batches 125 and 126.

## Batch 141 — The web app ships no Content-Security-Policy and can be framed
**Commits:** `591d0c2` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,208 backend and
1,140 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed (35 tests)

### Key facts for future sessions
- **Vite does not minify inline HTML scripts.** `dist/index.html` carries the theme script
  byte-for-byte, which is what makes a hard-coded `'sha256-…'` safe. `src/test/csp.test.ts`
  recomputes it from `index.html`, so editing that script without updating `vercel.json`
  fails the gate instead of blanking the theme in production.
- `connect-src` names **both** API origins on purpose: one `vercel.json` serves the
  production and staging Vercel projects and `VITE_API_URL` differs between them.
- `style-src 'unsafe-inline'` is deliberate and is the weakest directive in the policy.
  Radix, sonner and framer-motion all inject styles at runtime.
- `vite preview` does not apply `vercel.json`, so `e2e/prod-bundle-csp.spec.ts` reads the
  shipped policy out of that file and re-fulfils each HTML response with it. Its one
  deliberate difference is `connect-src` gaining `https://api.example.invalid`, which is
  what `ci-local.sh` builds the bundle against.
- That spec carries two guards-of-the-guard: one asserts the header actually reached the
  document, the other injects a script element and asserts the browser reports a
  `script-src-elem` violation — otherwise a silently broken listener would make every
  other case pass on a policy that blocked the whole app.
- Counts: FRONTEND 1,127 → 1,140.

**Next:** Batch 143, then its `/ship-prod`.

## Batch 143 — Logout leaves the last league on screen
**Commits:** `5c02dcd` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,210 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `LEAGUE_SWITCH_SCROLL_KEY` moved from `LeagueSwitchStrip.tsx` into `lib/leagueRecency.ts`,
  which now also exports `forgetLeagueContext()`. That keeps the key names in one place and
  stops `lib/` needing to import a component to clear them.
- The scroll key is **sessionStorage**, the recency key **localStorage**. Both are cleared.
- The clearing test asserts no `coupon_` key matching `/league/i` survives a logout, rather
  than naming the two. The defect was a `clearTokens` that only knew about tokens, so a
  third key added later has to fail in the gate and not on a shared laptop.
- `coupon_theme` is asserted to *survive* logout: the theme belongs to the device, not the
  account.
- `forgetLeagueContext` swallows storage exceptions independently per store — a private
  window or blocked site data must not stop a logout completing.
- Counts: BACKEND 1,208 → 1,210, FRONTEND 1,140 → 1,147.

**Next:** `/ship-prod` for Batch 143, then Phase 5 (159, 160, 161, 133, 162, 129, 147).

## Batch 159 — The hourly slate refresh walks every competition
**Commits:** `d1d4b60` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,215 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- The fix is one argument — `competition_ids=pooled or None` — and the `or None` is the
  ratchet release the daily run already had: an empty pool must walk everything or a fresh
  deployment can never learn a competition.
- Cost model, stated once: `windows x dates x competitions`, one `/events` request per
  competition, and `odds_api.fetch_slate` filters its own league list by `competition_ids`,
  so a narrowed id the provider does not carry costs nothing.
- **The competition pool is deployment-wide**, so any test that counts `len(pooled)` is
  measuring whatever the rest of the suite has already committed. My first version of these
  tests did exactly that: green alone, red in the full gate. They now charge each walk on
  its **intersection with the fake catalogue**, which is both what the real provider does
  and stable under a dirty pool.
- Two existing `run_refresh_slate` tests needed `pooled_competition_ids` patched, the same
  way the daily-run tests already did. Their assertions are unchanged.
- Verified non-vacuous by deleting the argument from `run_refresh_slate` — five tests red.
  Note the string `competition_ids=pooled or None` appears in **both** scheduler jobs, so a
  naive `replace(..., 1)` edits the daily job instead and proves nothing.
- Counts: BACKEND 1,210 → 1,215.

**Next:** Batch 160.

## Batch 160 — The request counter cannot see the requests that matter most
**Commits:** `8b1aa0d` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,225 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `OddsApiProvider.requests_made` is incremented in `_get` and nowhere else. Every request
  the client sends — slate walks, settlement lookups, the league catalogue, odds — passes
  through that one function, so a counter anywhere else sees a subset.
- The cache charges the **delta** across each forwarded call via `_charging(estimate=...)`,
  falling back to the estimate when the wrapped provider does not expose `requests_made`
  (the fakes, Betfair). Charged in `finally`, because a call that raised still sent its
  requests.
- `fetch_odds` is deliberately *not* wrapped: it already charged, and wrapping it too would
  double-count. The tiers, the valve's thresholds and the reserve's size are untouched.
- **The reserve holds browsing, not picking.** `for_pick = not best_effort`, so
  `fetch_odds` is the pick path and is exempt; `fetch_odds_best_effort` is browsing and
  falls through to cached entries without raising. My first version of the reserve test had
  this backwards and expected `fetch_odds` to raise.
- `test_plan_counter.py` uses a provider that counts what an HTTP client would send rather
  than mirroring the cache's arithmetic, so the two numbers are independent answers.
- Verified non-vacuous by reverting the three entry points: nine of ten tests red.
- Counts: BACKEND 1,215 → 1,225.

**Next:** Batch 161.

## Batch 161 — Twenty leagues can spend ten times the provider plan
**Commits:** `39b299f` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,240 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `PICK_SUBMIT_INSTALLATION_LIMIT` is `50/hour;100/day` — the *same* numbers as the
  per-league bucket, on purpose. That figure was always derived from the installation
  ("what the hour leaves once peak browsing is subtracted") and merely keyed per league.
- Charged **after** the league bucket. A league at its own ceiling is refused without
  touching the deployment's allowance, which is correct because nothing went upstream.
  The residual over-count — league charged, installation refuses — is the safe direction.
- **A property was deliberately inverted.** `test_a_second_league_keeps_its_own_pick_budget`
  asserted a quiet league still picks while a busy one is spent out. With ~50 pick requests
  available in an hour, two leagues cannot both have 50, so that property was being paid for
  with budget the deployment does not have. It is now
  `test_a_second_league_is_bounded_by_what_the_deployment_has_left`, and its docstring
  carries the reasoning.
- The per-league bucket is not redundant: it still bounds one league to the plan's spare
  hour after a redeploy resets the in-memory installation counter, and it refuses first so
  the log names the league that spent it.
- `test_the_aggregate_bound_is_per_league_rather_than_per_installation` was renamed to
  `test_the_per_league_bound_alone_covers_only_a_league_or_two`; its assertions are
  unchanged, only its docstring, which described a residual that is now closed.
- Gate failure, attempt 1: I set BACKEND_TEST_COUNT to 1241 and the gate printed 1240 — a
  miscount on my part, not a removed test. Raised to the printed figure and rerun.
- Counts: BACKEND 1,225 → 1,240.

**Next:** Batch 133.

## Batch 133 — Daily discovery has no budget of its own
**Commits:** `a498e2a` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,245 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `discover_fixtures` takes `request_budget: int | None = None`. Default `None` means
  unbounded, so every caller that does not opt in behaves exactly as before; only
  `run_discover_fixtures` passes `settings.discovery_request_budget` (90).
- A walk is priced at `len(competition_ids)`, or `MEASURED_PLAYED_CATALOGUE` when the
  caller passed no narrowing — the honest stand-in for a number this function cannot ask
  the provider for.
- **The walk is interleaved by date rank**, not window-major. That was the load-bearing
  half: with a budget, window-major order costs the *last window entirely* while the first
  is still buying dates a fortnight out. Order within a rank is `by_window`'s insertion
  order, so it is stable and no window is systematically last.
- The budget stop is a `break` after a commit, not an exception, so Batch 119's
  "keeps every date it bought" property needed its own test on this path.
- Taken **after** Batch 159 deliberately (the run order says so): 159 halves what an extra
  window costs, which is the number this budget is sized against.
- One test I wrote was too weak and I caught it by reverting: `the last window is still
  served` originally asserted `len(windows) == 3`, which is trivially true. The fake now
  records the window of each walk and the test asserts all three were served.
- Counts: BACKEND 1,240 → 1,245.

**Next:** Batch 162.

## Batch 162 — Submitting a pick waits for every phone in the league
**Commits:** `c36beb4` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,249 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `_announce_after_response` takes **identifiers, not ORM objects**: the request's session
  is closed by the time a background task runs, so it opens `AsyncSessionLocal()` and
  reloads the league and round. A league deleted in between is a clean no-op.
- `record_completion` deliberately stays inline. It is a durable write, and it is what
  makes the move safe — a fan-out that never ran leaves `delivered_at` null and the next
  pick on the round retries it (Batch 107).
- **Under `ASGITransport` a background task still completes before the response is
  observed**, which is why all 89 existing notification tests passed unchanged. That is
  also why "is it really off the request path?" cannot be measured with httpx timings.
- The new test wraps the app in an ASGI middleware that timestamps the final
  `http.response.body`, uses a 20 ms fake send, and asserts time-to-body < fan-out time.
  Reverting to an inline `await` turns it red at both 12 and 50 members.
- Counts: BACKEND 1,245 → 1,249.

**Next:** Batch 129, then 147, then the Phase 5 `/ship-prod`.

## Batch 129 — The alarms that watch for a silent scheduler only reach a dashboard
**Commits:** `2179fb5` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,257 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- The football-provider alarm **already pushed** (`notify_football_provider_trouble`). The
  gap was the discovery-silence one, which only logged. Only that half changed.
- The cooldown is `consume_durable_limit(session, "alert:discovery-silence", "1/day")` —
  the rate-limit counter table used as a durable "once per window" record. It survives a
  redeploy, which an in-process timer would not, and it needs **no migration**. The
  alternative was a new `ActionType`, and `ALTER TYPE ... ADD VALUE` is irreversible
  against a production database with no restore point.
- `notify_discovery_silence` checks `health.alarm` itself rather than trusting the caller.
- Gate failure, attempt 1: two of my new tests asserted an exact recipient list and an
  exact body. Both read **deployment-wide** state — `_admin_players` returns every site
  admin in the database and `leagues_without_open_round` every silent league — so they
  passed alone and failed in the full suite, where other modules' admins and leagues are
  committed. The copy test now builds a `DiscoveryHealth` directly, and the recipient test
  asserts membership rather than identity. Same class of mistake as Batch 159's pool count.
- The scheduler wiring has its own test: removing the call left every trigger-level test
  green, because they call `notify_discovery_silence` directly.
- Counts: BACKEND 1,249 → 1,257.

**Next:** Batch 147, then the Phase 5 `/ship-prod`.

## Batch 147 — The reminder job skips the repeated hour when the clocks go back
**Commits:** `665e266` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,260 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `pick_reminders` is the **only** domain job on UTC. The others stay on Europe/London
  because their wall-clock hour is the point (06:00 discovery, 14:30-adjacent passes); the
  reminder's is not — it only has to fire once an hour, and UTC is the one zone where
  "once an hour" is always true.
- The minute is unchanged at :15. London's offsets are whole hours, so the separation from
  `open_gameweeks` (:01) and `lock_gameweeks` (:00) is exactly as before.
- `test_create_scheduler_domain_jobs_fire_on_uk_wall_clock` no longer lists
  `pick_reminders`; it now asserts explicitly that this one is *not* on Europe/London, so
  the exception is stated rather than merely absent.
- The DST tests enumerate the trigger's real fire times across 2026-10-25 rather than
  reasoning about them, and a companion asserts the London cron still skips an hour — so
  an APScheduler change that fixed it upstream would surface here instead of leaving a
  pointless batch in place.
- Counts: BACKEND 1,257 → 1,260.

**Next:** the Phase 5 `/ship-prod`, carrying 159, 160, 161, 133, 162, 129 and 147.

## Batch 130 — A round completed by someone leaving never announces itself
**Commits:** `092ff38` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,269 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `complete_rounds_after_roster_change(session, league_id)` re-evaluates every pickable
  round and returns the ones whose completion row it wrote.
  `settle_completion_after_roster_change` wraps it with the announcement, its own commit
  and its own exception swallowing — leaving a league must not 500 on a dead subscription.
- Three call sites: `leave_league`, `remove_member`, and the site-admin `delete_player`
  (which loops the member's leagues). All three are tested **over HTTP**, because a
  service-level test passes against an app that never calls the service.
- **`final_picker_id is None` is not the roster-change marker.** The column has been
  nullable since long before this — the FK is `ON DELETE SET NULL` — so a null id also
  means "the member who completed this has since been deleted", and that row still has a
  name to print. The discriminator is the empty **name**; keying on the id rewrote those
  alerts and every pre-`024` legacy row too. The full gate caught it via
  `test_a_completion_written_before_024_falls_back_to_what_it_has`.
- `record_completion`'s picker/market/outcome/fixture parameters are now optional, which
  is what lets one function serve both paths.
- Also fixed a flake this session introduced in Batch 141: the CSP spec's `page.route`
  handler could still be fetching a font when the page closed. Routes are drained in
  `afterEach`, and the font assertion now actually checks a woff2 was fetched — its
  listener had been attached after the navigation that issues the request.
- Counts: BACKEND 1,260 → 1,269.

**Next:** Batch 131 — the win-rate oracle, decided by the owner.

## Batch 131 — A void pick lowers win rate exactly like a loss
**Commits:** `8eff2bb` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,271 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- **The oracle change, quoted.** Before:
  `"win_rate_pct": round(100 * len(won) / len(played)) if played else None`
  After:
  `"win_rate_pct": round(100 * len(won) / len(priced)) if priced else None`
  Owner's decision, 2026-09-23. The old form is quoted in a comment beside the new one so
  the change is legible from the test rather than from a commit message.
- Both surfaces moved together: `services/scoring.py` (per league) and `routers/me.py`
  (cross-league summary). Leaving either behind reintroduces the profile/summary
  divergence `Standing.win_rate_pct` was centralised to prevent.
- No priced picks → `None`, never 0% and never 100%. The UI already renders `null` as an
  em dash with an explanatory line, so no client change was needed.
- The regression tests are deliberately **uneven** (1-in-3, 3-in-4). A 2-win/2-loss record
  is 50% under either denominator, so a test built on that shape proves nothing.
- **Follow-up for the owner, not done here:** `PlayerProfilePage.tsx` shows "Nothing has
  settled yet — a win rate appears after the first result." when `win_rate_pct === null`.
  That is now also the state of a member whose only picks were voided, for whom something
  *has* settled. Copy is outside this row's scope boundary, so it is left as-is.
- Counts: BACKEND 1,269 → 1,271.

**Next:** Batch 132.

## Batch 132 — Declaring an extra week renames a round already played
**Commits:** `efdfdeb` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,278 backend and
1,147 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `declare_extra_week` takes `today: date | None = None` so the past-date guard is
  testable. Refusals: `EXTRA_WEEK_IN_THE_PAST` (422) and `EXTRA_WEEK_LOCKED` (409, a
  `PermissionError` — the endpoint gained that handler, which it did not have).
- The settled lock is **the football week, not the season**: Wednesday-to-Tuesday around
  the canonical Saturday, which is the span a declared date can relabel. Locking the
  season would refuse every declaration after the first settlement.
- `reanchor_from_earliest_round` runs from `sync_slate` after each round is written.
  Earlier only, and only while nothing in the season has settled — the same rule
  `move_anchor` enforces, applied automatically.
- **`season_calendar` cannot import `gameweek`**: that module imports this one, so
  `uk_today` is computed locally. mypy passed the circular import happily; importing
  `src.main` is what caught it. Worth remembering for any future shared helper.
- The end-to-end anchor test runs in **season 2031**. Calendar creation and re-anchoring
  are both deployment-wide reads, and the full suite commits 2026 rounds (settled ones
  included) from other modules — so it passed alone and failed in the gate until moved.
  That is the fourth deployment-wide-read trap this session.
- `test_stored_anchor_survives_a_later_added_earlier_round` is untouched and still right:
  `labels_for_gameweeks` never moves an anchor. Only discovery does.
- Counts: BACKEND 1,271 → 1,278.

**Next:** Batch 156.

## Batch 156 — A voided leg's price still multiplies into the combined coupon
**Commits:** `46b8d29` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,281 backend and
1,154 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- `combined_odds` is unchanged and stays pure arithmetic. `build_coupon` filters void
  before calling it, so the rule about void lives with the data that knows about it.
- `Coupon.void_leg_count` is **optional with a default of 0** — the Batch 67 rule for
  every field added to this response, because the web deploys from `main` while the API
  waits for `/ship-prod`. The web reads it as `?? 0`, which is also correct for a round
  with no voids.
- The voided leg stays on the coupon with its frozen price. Only the product changed.
- `voidLegLabel` is exported from `lib/share.ts` so the screen and the clipboard use one
  phrase; the agreement between them is asserted as a property over one and two voids.
- Each surface is covered independently: reverting `share.ts` alone or `CouponSection.tsx`
  alone turns three tests red each time.
- Counts: BACKEND 1,278 → 1,281, FRONTEND 1,147 → 1,154.

**Next:** Batch 157, then the Phase 6 `/ship-prod`. Phase 7 is deliberately not started.

## Batch 157 — The cross-league summary aggregates rank, which the contract says it does not
**Commits:** `e8b5fe4` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,281 backend and
1,154 frontend tests passed, 0 skipped; production-bundle Playwright smoke passed

### Key facts for future sessions
- Owner's 2026-09-22 decision was **drop the pair**, not refine the mean. `avg_rank`,
  `avg_rank_leagues`, `_MIN_MEMBERS_FOR_AVG` and `ranks_for_avg` are all gone from
  `routers/me.py`. `member_counts` stays — it still feeds `PerLeagueSummary.member_count`.
- **This is the one batch whose halves ship in the safe order by default.** Everywhere else
  the web deploying first is the hazard; here it is the fix, because the web must stop
  reading the field before the API stops sending it. Both halves are in one commit, so the
  push takes the web off it immediately and `/ship-prod` follows.
- Three tests pin the absence, each proved non-vacuous by re-adding the fields as optional
  with defaults and watching it fail:
  - backend, exact-shape: `test_cross_league_summary_shows_an_unpicked_round_and_no_leagues`
    asserts the whole empty-summary dict, so any field appearing or vanishing is caught.
  - backend, renamed-revival: `test_the_summary_averages_no_rank_across_leagues_of_different_sizes`
    asserts no top-level key contains "rank" at all, so `mean_rank` would fail too. It keeps
    the old test's setup (a 3-person and a 2-person league, ranks 2 and 1) because that is
    the case that made the old average wrong.
  - frontend: `/rank/i` must not match inside `career-stats`; the explanatory line sits
    outside that container, so a match in there can only be a rank statistic.
- The old backend test asserted `avg_rank == 2.0` and `avg_rank_leagues == 1`. Quoted in
  the replacement's docstring rather than deleted, so the removed behaviour stays readable.
- Net frontend count would have fallen by one (two obsolete tests removed, one added). The
  gate refuses a fall and the baseline may never be lowered, so the gap is filled by a real
  test, not padding: the page must ignore the dead fields during the window where the
  unshipped API still sends them. Counts unchanged: BACKEND 1,281, FRONTEND 1,154.
- The stat grid went `sm:grid-cols-4` → `sm:grid-cols-3`, and the loading skeleton from four
  boxes to three, so neither leaves a hole where the fourth card was.

**Next:** the Phase 6 `/ship-prod`, which carries Batches 130, 131, 132, 156 and 157.
Phase 7 is deliberately not started.

## fix/round-population-window-clock — a red baseline on main, fixed before Batch 144
**Commits:** `2f7d742` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,282 backend and
1,154 frontend tests passed, 0 skipped

### Key facts for future sessions
- **`main` went red with no commit behind it.** The gate was green at `42e79d8` at 16:45 UTC
  and red at 20:39 the same evening. The cause is the wall clock, not the code.
- Four tests in `test_round_population.py` named a fixed weekday for a league's slate
  window. Batch 112 refuses to create a round after its lock, so once the clock passes that
  weekday's window time, **today's cadence date is skipped for a reason the test never
  meant** and the horizon it asserts on is one date short. Wednesday 19:15 and 20:45 broke
  two of them that evening; the other two were waiting for a Thursday.
- The fix is the file's own `_future_window`, which Batch 112 added with a docstring saying
  not to name a weekday. It had simply not been applied everywhere.
- **How the set was measured, which matters more than the fix:** force every window onto
  today and run the file. A first, cruder sweep also flattened the minutes and implicated
  eleven tests — three of those failed only because two windows in one test collapsed onto
  each other, and three more use `_future_window` already and failed only because the sweep
  broke that helper. Re-running with the minutes preserved gave the real set of four.
- `_future_window`'s invariant is now a test rather than a convention: it never lands on
  today for any `days_ahead` in 1..6, asserted across the whole week. `days_ahead=0` fails it.
- Counts: BACKEND 1,281 → 1,282.

**Next:** Batch 144, which was parked on `feat/batch-144-project-round-labels` when this
turned up.

## Batch 144 — Home reads every round in the deployment, twice, to draw its labels
**Commits:** `1bfe512` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,285 backend and
1,154 frontend tests passed, 0 skipped

### Key facts for future sessions
- A round label depends on **every date that season's rounds fall on, deployment-wide** —
  that is what makes a label a shared idea rather than a per-league one, and it is the
  whole cost of labelling. It does not vary with which rounds are being labelled.
- `SeasonLabels` is the per-request resolver. It caches **misses as well as hits**, so a
  season with no calendar is not re-queried at the next call site. It is only valid while
  the rounds it covers are unchanged: **build one per read request and let it go — a
  request that creates rounds must not share one across that write.** Said in its docstring.
- `labels_for_gameweeks` survives as the single-use wrapper for the four call sites that
  label one set (gameweek.py twice, leagues.py, scoring.py). Nothing else changed.
- The read is now `SELECT DISTINCT gameweeks.starts_on`, which cannot return more rows than
  the season has distinct dates however many leagues played them, and never builds a
  `Gameweek`. Measured on one shape: **14 statements → 12**.
- The endpoint's docstring said nine queries when there were thirteen. It now lists eleven
  and names the conditional twelfth (the second standings read, which runs only when a
  settled round falls inside the season the table covers).
- `tests/test_cross_league_summary_cost.py` gives **each test its own season (2041–2043)**.
  These reads are deployment-wide and the suite shares one database; a count over the
  season being played would count whatever else the run had committed. Fifth time this
  trap has appeared — see Batches 159, 129, 133, 132.
- Both halves proved non-vacuous by reverting: undoing the sharing turns two tests red,
  undoing the projection turns all three red.
- Counts: BACKEND 1,282 → 1,285.

**Next:** Batch 145.

## Batch 145 — The biggest thing a member downloads is served uncompressed
**Commits:** `f929c3d` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,289 backend and
1,154 frontend tests passed, 0 skipped

### Key facts for future sessions
- **`BaseHTTPMiddleware` defeats `GZipMiddleware`'s size floor, and this is the thing to
  remember.** `add_middleware` prepends, so the last added runs outermost. Both
  `CorrelationIdMiddleware` and `SecurityHeadersMiddleware` are `BaseHTTPMiddleware`, which
  re-emits every response as a *stream*. Gzip above them never sees a content-length, takes
  the streaming branch, and compresses everything however small. With it outermost a
  658-byte login came back gzipped. **Gzip is therefore added first, innermost, below CORS.**
  Any new middleware added before it in the file will silently undo this.
- The floor is **4096**, not Starlette's 500, because a compressed response leaks its own
  length and everything under 4 KB here carries credentials. The login response is **658
  bytes**, measured. A test asserts it is both uncompressed *and* under the floor, so the
  day it grows past 4 KB that test fails rather than the response quietly compressing.
- `compresslevel=6`, not 9: the last three levels buy about a percent on this payload for
  several times the CPU, and below `thread_minimum_size` (128 KiB) it runs on the event loop.
- Measured: **23,205 bytes of JSON → 3,131 on the wire** (12 members, 60 fixtures). The test
  bound is 3x rather than 7.4x so a library upgrade moving gzip's output a few percent does
  not turn it red.
- `content-length` on a compressed response is the *compressed* size and survives the
  streaming layers above; `response.content` under httpx is decoded. That pair is the
  measurement.
- Three separate reverts prove three separate decisions: no middleware (2 tests red), gzip
  outermost (2 red, including the credential one), floor at 500 (1 red).
- **Production's `content-encoding` and `vary` are still unconfirmed** — the reverse proxy
  is the other half of this finding and only production has one. Check at the shipment.
- Counts: BACKEND 1,285 → 1,289.

**Next:** Batch 128, pulled forward ahead of 146 by owner decision (23 Sep) because 146 is
the plan's only migration and removes the rollback target.

## Batch 128 — Every shipment that carries a migration leaves nothing to roll back to
**Commits:** `00d609e` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,297 backend and
1,154 frontend tests passed, 0 skipped

### Key facts for future sessions
- **Pulled forward out of Phase 9 by owner decision (23 Sep) so it lands before Batch 146**,
  the plan's only migration.
- The rule: a batch that adds a revision writes `docs/runbooks/migration-NNN-recovery.md`
  as part of that batch. `docs/runbooks/migrations.md` is the convention;
  `migration-016-recovery.md` is the worked example.
- **Two enforcement points, one definition of "usable".** The batch half is a *test*
  (`test_migration_recovery_gate.py`) — add a revision past 025 with no plan and the gate
  goes red on your own branch. The shipment half is `scripts/check-migration-recovery.sh`,
  wired into `/ship-prod` step 1.7, which reads the deployed revision from production's
  `/api/v1/health` so a stale note cannot satisfy it. The test calls the script's
  `--plan-for` mode rather than restating the rule.
- **The batch half is deliberately not a hook in `check-closeout-safety.sh`.** That file is
  in `assert-quality-guardrails.sh`'s PROTECTED list, so a batch editing it fails its own
  gate — correctly. I wrote that hook first, hit the guardrail, and moved it. The test is
  the better home regardless: it runs on every batch and in CI, not only at close-out.
- **Exit 2 (unknown deployed revision) is not a pass.** An unestablished starting point
  means the applied set is unknown, not empty. Waving it through would let past exactly the
  shipment this exists to stop. Asserted by its own test.
- The contracting-DDL report scans **`upgrade()` only** — every `downgrade()` drops what its
  upgrade created, so scanning whole files would flag all 25 revisions and mean nothing. It
  reports rather than refuses: sometimes contracting is the point, but the plan must say why
  it could not wait. `create_table` with NOT NULL columns is not contracting and is not
  reported.
- **bash 3.2 traps hit while writing this**, both of which pass `bash -n`: `mapfile` does not
  exist, and `local a="$1" b="$a..."` leaves `b` interpolating an *unset* `a`, which under
  `set -u` is a hard error. macOS ships 3.2 and the local gate runs on it.
- Revisions 017–025 are **not** backfilled: deployed already, neither check fires, and the
  convention starts from 026. Their plans, where written, are sections of the L4 doc.
- Counts: BACKEND 1,289 → 1,297.

**Next:** Batch 146 — the plan's only migration. It now needs
`docs/runbooks/migration-026-recovery.md` before it can close out, which is the whole point
of taking this batch first.

## Batch 146 — The queries that sweep rounds cannot use the indexes that exist
**Commits:** `ee3d196` · verified: `scripts/ci-local.sh` PASS (11 checks), first run; 1,300
backend and 1,154 frontend tests passed, 0 skipped

### Key facts for future sessions
- **Migration `026`** — the plan's only one. Purely additive: two `CREATE INDEX`, nothing
  dropped, renamed, altered or rewritten. `docs/runbooks/migration-026-recovery.md` is its
  forward recovery plan, the first written under Batch 128's convention, and it passes that
  gate (94 lines).
- **The rollback is blocked by bookkeeping, not by schema.** The `025` image reads and
  writes both tables exactly as before — nothing names an index. What stops it booting is
  `alembic_version` reporting `026`, which its history cannot resolve, so `upgrade head`
  fails before uvicorn binds. If a rollback is ever genuinely needed, the recovery note's
  answer is: set the version row back to `025`, **leave the indexes in place**, roll the
  deployment. Owner authorisation required; the indexes are invisible to that image.
- `downgrade()` is **lossless at any time** — an index carries nothing not derivable from
  the table. Unusual here; every migration since `016` has not been.
- **The tests ask the planner, they do not assert an index exists.** At production's size
  (87 picks, 24 gameweeks, measured 2026-09-23) PostgreSQL sequentially scans either way
  and is right to, so the tests seed 6,000 rounds and 20,000 picks, `ANALYZE`, and read
  `EXPLAIN (ANALYZE, BUFFERS)`. Before: `Seq Scan on gameweeks (cost=0.00..165.01)`. After:
  `Index Scan using ix_gameweeks_starts_on (cost=0.28..8.58)`.
- **Everything in that file rolls back.** 20,000 committed picks would slow the whole suite
  and corrupt every deployment-wide count it takes — the trap this run has hit five times.
  `ANALYZE` inside the transaction does see the uncommitted rows, which is what makes it work.
- Two SQL traps inside `text()`: `:first::date` is a syntax error because `::` collides with
  the bind-parameter marker — use `cast(:first as date)`; and `date + interval` is not a
  date, so `starts_on` needs `cast(:first as date) + n`.
- A third test pins the other direction: a read that *does* know its league must still take
  `ix_picks_league_gameweek`, so the new index does not become the planner's default for
  everything.
- **Pool: 10 + 10 → 5 + 5, with an explicit `pool_timeout=10`.** Production's
  `max_connections` is **60** and about **15 backends** are already Supabase's own — twenty
  from one container was a third of the instance. If this is ever wrong the symptom is
  `TimeoutError: QueuePool limit ... reached` ten seconds into a request.
- Counts: BACKEND 1,297 → 1,300.

**Next:** Batches 163, 164, 165, 166 (all web-only), then the Phase 7 `/ship-prod` — which
carries migration `026` and needs the owner's written approval of the recovery plan first.

## Batch 163 — The service worker downloads the whole app, including screens a member cannot open
**Commits:** `ba3f580` · verified: `scripts/ci-local.sh` PASS (11 checks), first run; 1,300
backend and 1,160 frontend tests passed, 0 skipped

### Key facts for future sessions
- Measured on this build: **979.0 KiB precached → 917.2 KiB**, 13 chunks (61.9 KiB) left on
  demand. That is **6.3%**, less than the finding's framing implies — most of the 979 KiB is
  the shell and the routes members actually use, and those should be precached. Said plainly
  rather than dressed up.
- **The rename is the load-bearing part, not the filter.** `pages/admin/DashboardPage.tsx`
  and `pages/admin/ResultsPage.tsx` emitted `DashboardPage-*.js` and `ResultsPage-*.js` —
  the *same* chunk basenames as the member-facing pages. A prefix filter over that layout
  would have stopped precaching **home**. All seven admin pages are now named after their
  exported components (`Admin*Page`), and a test fails if one is added without the prefix.
- The per-league console (`/leagues/:slug/admin/*`) is five pages that share no prefix with
  each other and sit beside member pages, so they are listed by name in
  `LEAGUE_ADMIN_PAGES`. **Two tests keep that list honest in both directions**: every
  `/leagues/:slug/admin/` route `App.tsx` declares must be matched, and every name in the
  list must still appear in `App.tsx`. Both read the file rather than restating it.
- The filter lives in `lib/precacheFilter.ts`, not inline in `sw.ts`, so it is testable.
- **`vite.config.ts` is the obvious home for a precache change and is a PROTECTED gate
  file** — `assert-quality-guardrails.sh` refuses a batch that edits it. Filtering the
  injected `self.__WB_MANIFEST` inside the service worker needs no build-config change.
  Second time this run that a protected file forced a better design (see Batch 128).
- Parsing the built manifest: the injected array uses **quoted** keys — `"url":"assets/…"`
  — not `url:`, which is workbox's own minified internals. Matching the wrong one silently
  reports zero entries.
- Counts: FRONTEND 1,154 → 1,160.

**Next:** Batch 164.

## Batch 164 — An animation library is a seventh of the JavaScript and mostly unused
**Commits:** `7e37b9b` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,300 backend and
1,167 frontend tests passed, 0 skipped

### Key facts for future sessions
- Measured: the **109 KiB framer-motion chunk is gone**; precache manifest **979.0 → 847.5
  KiB**; what the service worker downloads **917.2 → 785.7 KiB** (with Batch 163's filter).
- **`PageTransition` lost its exit animation and that is a real behaviour change.**
  `AnimatePresence mode="wait"` slid the outgoing page away over 220ms *before* the
  incoming one began. CSS cannot animate an element React has unmounted. A route change is
  now 220ms rather than 440ms with no blank moment. Restoring the exit means keeping the
  old tree mounted, which is what cost 107 KB.
- **`layoutId` was the only thing that genuinely needed framer.** `useSlidingIndicator`
  replaces it: one measured element per bar, positioned from the **active element's own
  box** — not index × width, because the tabs are not equal width and the bottom bar shows
  four or five items by route. `useLayoutEffect` not `useEffect`, or it flashes at the
  container's left edge on first paint. A `ResizeObserver` catches rotation, late fonts and
  the iOS keyboard; a window-resize listener would catch only the first.
- **Reduced motion is now one rule in `index.css`, not a hook per component** — and that
  fixed a real gap: `PageTransition` and the save button called `useReducedMotion`, `TabBar`
  never did. The media block also zeroes `--page-enter-x`, because collapsing a duration
  still leaves one frame of displacement if the animation starts 16px off.
- The save button's tick is `stroke-dasharray` + animated `stroke-dashoffset` —
  the technique framer's `pathLength` wraps. `--check-length` must be **≥** the path's true
  length; too short leaves the tick visibly pre-drawn.
- TabBar's More button needs **two refs on one element** (active indicator + the sheet's
  focus anchor), so a callback ref assigns both — and `useRef<T | null>(null)`, because
  `useRef<T>(null)` infers a read-only `RefObject`.
- The indicator moving out of the button meant "More is current" had to be said in the
  markup: it now carries **`aria-current="page"`**, which a screen reader was never told by
  the coloured span. The test asserts both directions.
- **JetBrains Mono 700 removed.** Nothing used a bold mono weight — the only reference was
  its own `@font-face` — so no browser fetched it, but the SW precached 21.9 KB on install.
- **framer-motion is still declared in `package.json`**, a PROTECTED gate file. Nothing
  imports it so nothing bundles it, and `animations.test.ts` keeps that true. Removing the
  declaration needs a gate-maintenance batch. Third protected-file collision this run.
- `animations.test.ts` also asserts every `animate-*` class used in source exists in
  `index.css` — a typo'd class renders a fine element with no animation, which reads as a
  design choice rather than a bug. `tailwindcss-animate` supplies `animate-in`/`animate-out`.
- **Not done: Lighthouse on home.** Bundle bytes are measured and the CSS verified in a real
  browser at 375px, but no Lighthouse run — see the overnight log.
- Counts: FRONTEND 1,160 → 1,167.

**Next:** Batch 165.

## Batch 165 — The lock countdown re-renders the entire pick screen once a second
**Commits:** `13e49b4` · verified: `scripts/ci-local.sh` PASS (11 checks); 1,300 backend and
1,180 frontend tests passed, 0 skipped

### Key facts for future sessions
- **The third finding was a live bug, not hygiene.** `LeagueActionsMenu` invalidated
  `['leaderboard', slug]` after leaving a league; **no query has ever been keyed
  `leaderboard`** — the tables are keyed `standings`. It cleared nothing, silently, leaving
  a member looking at the table of a league they had just left. React Query cannot warn:
  a key matching no query is an ordinary thing for a key to do.
- `lib/queryKeys.ts` is the factory. Its rule: **a key names every input its request
  depends on.** `standings.forSeason(slug, null)` spells `null` as `'current'`, because a
  request where the API chooses the season is a *different* entry, not an absent one.
- **The key shapes are deliberately unchanged.** `['league', slug]` is both the detail
  query's own key and the prefix its children hang off, and `LeagueAdminInvitesPage` writes
  to it with `setQueryData`, which matches exactly rather than by prefix. Members and
  seasons still live on their own roots, and a test states that rather than assuming it.
  Reshaping is a later batch and is now one edit here.
- `useExpiry` replaces `useCountdown` wherever only the **boolean** was wanted: one
  `setTimeout` to the boundary instead of a 1 s interval. `<Countdown>` is `memo`'d and owns
  the tick. **`format` is a prop** because the two screens word the remaining time
  differently and unifying them would change what a member reads on one of them.
- **`setTimeout` clamps above ~24.8 days and fires immediately**, so a naive version would
  report a round two months out as already locked and the pick screen would open shut.
  `useExpiry` re-arms in day-long hops. Its own test.
- Measured, as the row asks: commits per idle five seconds on a screen with a live clock,
  **2 → 1** under fake timers. Five ticks inside one `act()` batch into one commit, so the
  fake-timer figure understates it; in a browser each tick is its own commit.
- A trap that looked exactly like a bug in the hook: a target computed from `Date.now()`
  **inside** the component recomputes every render, so the deadline runs away and never
  arrives. Hoist it — a real page passes an instant from the API.
- Both context values are now `useMemo`'d. Their callbacks were already `useCallback`.
- **Frontend baseline note:** the gate printed 1180 where the arithmetic said 1179. The
  count was stable across three consecutive runs, so the baseline was raised to what the
  gate printed — the one permitted adjustment.
- Counts: FRONTEND 1,167 → 1,180.

**Next:** Batch 166, which the plan says to take last and re-measure first.

## Batch 166 — PARKED, not started
**Branch:** none. Nothing was written.

### Why
The row's verification is explicit: *"Lighthouse mobile re-run on standings, median of
three, **with the blocking time attributed to a named cause before any change is made**"* —
and the row itself warns that chasing the 915 ms before 164 and 165 land "risks optimising
the wrong thing".

The standings screen is behind authentication and needs a league with members and settled
rounds. Measuring it means signing in as the owner, which I will not do, and Lighthouse's
throttled mobile profile is not something the tools here can drive anyway.

So the prerequisite the row makes mandatory cannot be met, and everything after it is
guesswork. **Batches 164 and 165 both removed plausible causes** — 109 KiB of JavaScript,
and a per-second re-render of whole screens — so there is a fair chance the figure has
already moved a long way. That is a reason to re-measure, not a substitute for it.

### What unblocks it
One Lighthouse mobile run on the standings screen of a real league, median of three,
against production. Then either the finding is closed because the number came down, or the
remaining blocking time has a named owner and the batch has something to act on.

### A local measurement, taken 2026-09-24 — supporting, not conclusive
Production's standings is behind a sign-in that is not mine to perform, so this was
measured against a **locally seeded** Coupon instead: same client bundle, a league of 12
members with 10 settled rounds, a throwaway Postgres, Playwright's Chromium at Lighthouse's
mobile profile — 412x823, DPR 1.75, **CPU throttled 4x** by CDP.

**Median total blocking time over three runs: 109 ms** (598 / 102 / 109). The 598 is the
first cold load, dominated by a single 397 ms task; the warm runs sit near 100 ms with no
task over 101 ms. Three CPU profiles agree the main thread is **58–70% idle** through the
load.

**This is not comparable to the review's 915 ms and must not be quoted as "915 → 109".**
Different machine, and Lighthouse throttles the network as well as the CPU and measures TBT
only between FCP and TTI. What it does support is that the current code shows no sign of a
second-long block on this screen.

**The largest named *application* cost is `useSlidingIndicator`** — 20–26 ms, 2.3–4.1% of
samples, consistent across all three profiles. That is [[batch-164]]'s own tab-indicator
hook, which reads `getBoundingClientRect` in a layout effect. Everything else identifiable
is React internals under 10 ms. So if 166 does find work to do, that hook is the first
place to look — and it arrived *after* the review measured the screen.

Method notes worth keeping, because both would have produced a confident wrong answer:
- A `PerformanceObserver` armed with `page.evaluate` before `goto` measures **nothing** —
  the navigation replaces the document and takes the global with it. It reported TBT 0.
  Use `addInitScript`, and assert the array exists rather than defaulting it to `[]`.
- Logging in once per run trips the app's own durable login limit (5 per 15 minutes) on the
  third run. Sign in once and reuse `storageState`.

## Phase 7 shipment — REFUSED BY RAILWAY, nothing shipped (2026-09-24)
**Attempted commit:** `8d898b4f` (Batches 144, 145, 146, 128 + migration `026`)

- Preflight and source verification passed in full; owner approved the `026` recovery plan.
- IaC redeploy `29f319d7-85ee-4136-8066-c7b1f1879ca7` SUCCESS. `railway up` then failed:
  `configErrors: ["Failed to create code snapshot..."]`, deployment
  `74baee41-fb1d-4eec-898c-7a6a5cc65caa` FAILED at **`SNAPSHOT_CODE`** — the upload step,
  the only deployment event recorded.
- **Migration `026` did not apply.** `/api/v1/health/ready` reports the head the *database*
  is at and it says `025`. No image was built and no container started, so nothing ever
  reached the database.
- **Nothing to roll back**; production never left `29f319d7`. The one mutation was
  `RAILWAY_GIT_COMMIT_SHA`, stamped before the upload, reverted immediately and verified by
  **reading the variable back** rather than inferring it from `/health` — which reports the
  env snapshot of the container that started *before* either change and would have looked
  right either way.
- `check-deploy-drift.sh` now reports `DRIFTED — 5 of 19`, which is the truth.
- Rollback baseline for the retry is **`29f319d7`**, not `adc3c65e` — the IaC redeploy
  superseded it and Railway marked the older one `REMOVED`.
- **The Vercel CLI token in this environment has expired** (`invalidToken`). The web half
  was confirmed by fetching the live stylesheet and checking it carries Batch 164's rules
  and not the removed font — a stronger check than metadata, but the token needs renewing.
- Per the standing rule, the run stopped here rather than retrying.

## Phase 7 shipment — SHIPPED on the retry (2026-09-24)
**Commit:** `13431987`, carrying Batches 144, 145, 146 and 128 — **migration `026`**

- Railway `8701d8c3-7102-4fa5-a108-515bd762937e`, `SUCCESS`. Rollback baseline
  `673b9f15-4c81-492d-a498-290fc306de90` — but `026` has applied, so restoring it needs
  `docs/runbooks/migration-026-recovery.md`, not a plain redeploy.
- **The migration is proved applied by two independent readings**, not one: the deployment
  log records `Running upgrade 025 -> 026` completing before uvicorn bound, and
  `/health/ready` — which reports the head the *database* is at — returns `026`, agreeing
  with `/health`'s image head.
- Nothing changed between the refused attempt and this one except a docs commit. Same tree,
  same green CI, same green gate. That is the evidence the first failure was Railway's.
- Smoke: web root and deep link 200 and byte-identical with every committed security header;
  CORS 200 from the stable origin with credentials, foreign origin 400 and no ACAO; manifest
  1 replica `europe-west4-drams3a`, sleep off, IPv6 egress on, 0.25 vCPU / 500 MB. Logs 44
  lines, 0 errors, clean on all five leak patterns. `check-deploy-drift.sh`: **in sync**.
- **One preflight check was not completed.** The direct database session — RLS, the
  `anon`/`authenticated`/`PUBLIC` grant recheck, and confirming Batch 146's two indexes
  exist — needs the Supabase direct host, which resolves **IPv6-only**, and this machine
  lost its IPv6 stack mid-shipment (`ping6` could not reach a literal address). Same fault
  behind the first attempt's upload failure. Last verified in full on 2026-09-23 (21 of 21
  tables with RLS, no grants); `026` creates two indexes and touches neither. **Re-run it
  from a host with IPv6 before the next shipment.**
- **Batch 145 confirmed live in production, both sides of the threshold** (2026-09-24,
  after the shipment). No *successful* public response is over 4 KB, but a **422 from
  `/auth/login`** is unauthenticated, non-mutating and as large as the invalid input it
  echoes back — which makes it a probe for exactly this:
  - 3,407-byte body → **no** `content-encoding`. The floor holds.
  - 7,479-byte body → `content-encoding: gzip`, `content-length: **205**`, and
    `vary: Accept-Encoding` on both.
  That answers the question the batch could not: **the reverse proxy passes
  `content-encoding` through**, and production now sends `vary` where the finding recorded
  it sent none. (205 bytes is not a realistic ratio — the probe body is one repeated
  string. The realistic figure is the 23,205 → 3,131 measured on a real slate.)

## Batch 155 — Two people's real names and old sign-in names are in a public repository
**Commits:** `ca62213` · verified: `scripts/ci-local.sh` PASS (11 checks) on the first run;
1,300 backend and 1,180 frontend tests passed, 0 skipped

### Key facts for future sessions
- **Every non-owner member is "Member A" to "Member L" in the tracked tree** (no I; the owner
  stays "Craig"). A and B are the two Batch 74 renamed; the letters follow the 8 August
  slip's order, not the names. L0 already forbade committing real display names — never
  reintroduce one. The public git history still holds them; no rewrite was authorised.
- **The re-verification was the finding.** The row named two people in three documents; the
  names were in 16 files, including live boot-time code, and nine more members' names had
  never been flagged. The owner widened the scope to all eleven on 2026-09-24.
- **The rename notice is keyed by profile id** (`RENAMED_PROFILE_IDS`). Production read
  2026-09-24: owner and member A marked told; member B has no push subscription and is
  untold — Batch 148's case. The push no longer quotes the old name, and the marker records
  only the new one.
- **The two backfill scripts are records now, not runnable**: against production they stop
  at member resolution before writing anything.
- **Direct IPv6 to the Supabase host failed again (`gaierror`) and `railway ssh` worked** on
  2026-09-24 — the route has flipped again. Base64 a read-only asyncpg script into the
  container and run it with `/opt/venv/bin/python`.
- **The full gate took 13m09s** at these counts; the docs' "88 seconds" is Batch 153's job.

**Next:** Batch 154. `/ship-prod` is owed for this batch's API half.

## Batch 154 — Two documents cost 106k tokens to read and under 2% of one is current
**Commits:** `524e7ba` · verified: `scripts/ci-local.sh` PASS (11 checks) on the first run;
1,300 backend and 1,180 frontend tests passed, 0 skipped

### Key facts for future sessions
- **`STATUS.md` is one page of dated current state; rewrite a line, never append.** The old
  2,268-line page is archived verbatim at the top of this file, headings demoted a level —
  history, not state, and stale in places when moved.
- **`docs/BUILD_PLAN.md` opens with the open rows; closed rows are under `## Closed
  batches` at the end**, in written order. Read the head with
  `sed -n '1,/^## Closed batches/p'`. The split was scripted and asserted lossless.
- **A ticked row does not move by itself.** `/strike-batch` still only flips the box, so
  ticked rows collect in the open section until moved; this run moves each at close-out
  (154 went in before 155). Teaching `strike-batch.md` to move it is outside this batch.
- **Measured, not modelled:** the reads `/next-batch-prompt` instructs fell from 529 KB
  (~131k tokens) to 38 KB (~9k), and both reach Batch 95 — a byte count of the
  instructed reads, not a separate cold agent session.
- Production facts gathered for the page (read-only, 2026-09-24): migration `026`;
  `season_calendars` empty, so the calendar backfill is still the owner's; avatars off;
  the Vercel CLI token answers 403.

**Next:** Batch 153. `/ship-prod` is still owed for Batch 155's API half.

## Batch 153 — The instructions quote a gate that has not existed for a month, and the hook argues against the policy
**Commits:** `eabe49d` · verified: `scripts/ci-local.sh` PASS (11 checks) on the first run;
1,300 backend and 1,180 frontend tests passed, 0 skipped

### Key facts for future sessions
- **Measured 2026-09-24:** backend without a database 780 passed / 520 skipped; with one
  1,300 / 0; three full gates took 13m09s, 11m10s and 10m38s. Every quoted figure is dated
  now — rerun rather than trust one.
- **The guardrail can now record an owner-approved exception**: `approved_gate_maintenance`
  in `scripts/assert-quality-guardrails.sh` names a batch and the protected files it may
  change; it applies only on that batch's own branch while its row is open. Entries: 153
  (inert now it is ticked) and 127 (`ci.yml`, `ci-local.sh`, `apps/web/package.json`).
  Never add one without the owner's approval in the row.
- **Both stop hooks now say close-out is automatic** for a build batch with a green gate,
  and that a launch phase still waits — matching `AGENTS.md`.
- **The review's "fifteen queries" for `me.py` was already stale** (Batch 144 made it eleven,
  twelve when a rank can move); the module docstring now defers to the function's count.
  It is under `apps/api`, so close-out classed the batch API-only: no runtime change.
- This Mac's git is **2.16** — no `git worktree remove`; delete the directory and
  `git worktree prune`.

**Next:** Batch 127. `/ship-prod` is owed for Batches 155 and 153.

## Batch 127 — The web app is built and tested on a runtime that stopped receiving security fixes in April
**Commits:** `c9d0ed3` · verified: `scripts/ci-local.sh` PASS (11 checks) on the first run,
frontend on Node 24.21.0 / pnpm 9.15.0; 1,300 backend and 1,180 frontend tests passed,
0 skipped

### Key facts for future sessions
- **Node 24, not 22, by owner decision (2026-09-24).** The production Vercel project was
  already configured for 24.x and builds from `apps/web`; that package now pins
  `engines.node: "24.x"`, so the repo decides the Vercel runtime. CI, `ci-local.sh`,
  `.nvmrc`, `dev.sh`/`preview.sh` and the root floor (`>=24`) all follow.
- **pnpm under Node 24 is corepack's shim** (`corepack enable pnpm`), resolving
  `packageManager: pnpm@9.15.0` from the local corepack cache — no download. The gate's
  install step now refuses any other pnpm and says how to fix it (PIPE-09).
- **nvm's default alias is still 20** on this Mac; everything that matters selects 24
  explicitly. The Railway and Vercel CLIs stay installed under Node 20's globals, which is
  why the ship docs still name `v20.20.2` paths — those are CLI locations, not a runtime.
- **OPS-15 not taken:** Vite 5, ESLint 8 (9 needs flat config), Tailwind 3 and Vitest 2 are
  each a real migration.
- Protected files changed under the owner's named exception: `ci.yml`, `ci-local.sh`,
  `apps/web/package.json`. The 127 entry in the guardrail is inert now the row is ticked.

**Next:** Batch 142. `/ship-prod` is owed for Batches 155 and 153.

## Batch 142 — The cryptography pin has gone stale and web push has no timeout
**Commits:** `9b99f41` · verified: `scripts/ci-local.sh` PASS (11 checks) on the second run;
1,305 backend and 1,180 frontend tests passed, 0 skipped

### Key facts for future sessions
- **Gate failure, fixed on attempt 2:** the new hung-push test passed alone and failed in
  the full suite. `configure_logging` sets `cache_logger_on_first_use=True`, so
  `structlog.testing.capture_logs()` misses a module logger an earlier test already used.
  Patch the module's `log` object instead — no test here had asserted on logs before.
- **Every push carries `PUSH_SEND_TIMEOUT_SECONDS` (5).** pywebpush's own default is `None`,
  which it hands to `requests` — unbounded. A timeout logs "push send timed out" and does
  not count towards auto-disable. The test sends a real encrypted payload to a listening
  socket that never replies; with the timeout removed it hung past 25s.
- **Push endpoints must be on 443** (or no port) — the allowlist had named hosts only.
- **`cryptography` stays 48.0.1** (owner, 2026-09-22). OSV on 2026-09-24 lists exactly the
  three advisories `requirements.in` already documented as unreachable; their CVE/GHSA
  numbers are now beside them. `requests` is declared at 2.34.2, the version pywebpush
  already resolved; a fresh `uv pip compile` matches the lock below its header.
- API-carrying: `/ship-prod` owed now for 155, 153 and 142 together.

**Next:** Batch 95 — needs the owner's storage choice before any code.

## Batch 95 — The scored history of the game has no second copy
**Commits:** `98de5d2` · verified: `scripts/ci-local.sh` PASS (11 checks) on the second run;
1,321 backend and 1,180 frontend tests passed, 0 skipped

### Key facts for future sessions
- **Built switched off (owner, 2026-09-25): R2, EU jurisdiction, Mondays 04:00 London.**
  `BACKUP_STORAGE=s3` plus the `BACKUP_S3_*` variables turn it on; nothing is scheduled
  and no egress is spent until then. `docs/runbooks/backup-restore.md` has the owner's
  switch-on steps and the restore command. Production has no backup until then.
- **Order is the contract:** resolve target, list one key, then `pg_dump`, then upload.
  Failure writes `backup_failed` and pushes site admins (1/day cooldown, durable bucket
  `alert:backup-failed`); a half-configured switch also logs at boot.
- **A `--schema=public` archive restores only with `pg_restore --clean --if-exists`** — it
  carries `CREATE SCHEMA public`, which every new database already has. Found by the
  rehearsal test; never point `--clean` at a database holding data.
- **SigV4 is hand-rolled over httpx** (`services/backup_storage.py`), pinned to AWS's
  `get-vanilla` vectors (fetched from botocore's copy of the suite). R2 has **no
  write-only key** — the bucket lock is what protects old archives.
- **Gate failure, fixed on attempt 2:** `test_run_scheduled.py` pins the exact set of
  manually runnable jobs; adding `offsite-backup` meant adding it there (as Batch 119 did
  for its job) and pinning it to `run_offsite_backup` in the neighbouring test.
- pgserver ships PostgreSQL 16.2 client tools, so the rehearsal runs in CI too;
  production's image has the 17 client.

**Next:** Batch 134. `/ship-prod` owed for 155, 153, 142 and 95.

## Batch 134 — A mis-settled pick can only be corrected by running a script against production
**Commits:** `9731b4a` · verified: `scripts/ci-local.sh` PASS (11 checks) on the first run;
1,327 backend and 1,180 frontend tests passed, 0 skipped

### Key facts for future sessions
- **`POST /api/v1/admin/picks/{pick_id}/correct`** — site admins only; body is the true
  score or `void` plus a required `reason`. It re-scores one settled pick through
  `resolve_pick`, so there is still one scoring rule. A pending pick is refused (409): that
  is settlement's job. There is no screen for it yet — API only, as the row specified.
- **Standings need no recompute**: every table reads `picks` per request. The stored
  `standings` table is *football* league tables, not the member leaderboard.
- **Idempotent**: an unchanged result returns `changed: false` and writes no audit row.
  A change writes `league_updated` against `picks` with `action: pick_corrected`, both
  states, the result entered and the reason — no new `ActionType`, since `ALTER TYPE ...
  ADD VALUE` cannot be undone.
- **The gate took 38 minutes** (normally 11-13): macOS's storage-management processes
  pushed the load average to 58. Slow is not failing — check `uptime` before suspecting a
  hang; every Postgres backend was idle and the run was progressing.

**Next:** Batch 136 — needs owner decisions on erasure scope before any code.
`/ship-prod` owed for 155, 153, 142, 95 and 134.

## Batch 136 — A member cannot delete their account or get their data
**Commits:** `baae8ed` · verified: `scripts/ci-local.sh` PASS (11 checks) on the second run;
1,335 backend and 1,187 frontend tests passed, 0 skipped; browser-checked against a scratch
database

### Key facts for future sessions
- **Owner decisions:** anonymise and keep history (2026-09-22); erase everything naming
  them, show "Former member", immediately after the PIN, refused while sole admin of a
  league others play in (2026-09-25). Site admins cannot self-delete.
- **Memberships stay active on purpose** — standings count only active memberships, so
  ending them would erase the leaver's points from past tables. `deleted_at`/`is_active`
  on the profile is what hides them from rosters, reminders and round progress.
- **The stored name is `Former member <8 hex>`**; `display_name.public_name(_sql)` shows it
  as "Former member" on standings, results, coupon legs, "taken by", member lists, join
  requests and the activity feed. An unmapped read shows the placeholder, never a name.
  "Former member…" is reserved for registration and per-league names.
- **A wrong PIN is 403, not 401**: `apiFetch` treats 401 as an expired session and signs
  out. The Change PIN card still answers 401 — spun off as a separate task.
- **Gate failure, fixed on attempt 2:** `viewport.test.ts` generates one check per source
  file, so two new files meant +2 frontend tests beyond the 5 written (1,187, not 1,185) —
  proved by a per-file count with the web changes stashed.
- **Local browser check recipe:** a runner process holding pgserver + `tests.e2e_server`
  on :8000 with `FRONTEND_ORIGIN=http://127.0.0.1:4173`, `VITE_API_URL` set at build (the
  `.env.local` targets another product), then the `web-preview` launch config. Stop the
  *runner's* PID, not its shell wrapper, or pgserver's postgres outlives its data dir.

**Next:** `/ship-prod` (scheduled), then Batch 135.
