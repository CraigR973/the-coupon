# The Coupon — feature-completeness and product-gap review

Sources read in full: `AGENTS.md`, `docs/BUILD_PLAN.md` (2701 lines), `docs/LAUNCH_PLAN.md` (479
lines), `STATUS.md` "## Now"/"## Next"/"## Toolchain". Code checked directly for every Part B
claim via `apps/api/src/routers/`, `apps/api/src/services/`, and `apps/web/src/{pages,hooks,components}`.

---

## Part A — Spec vs. built

Every batch through 81 is checked `[x]` in `BUILD_PLAN.md`, and `STATUS.md`'s "Next" section
(line 1075) states "Everything specified is shipped" as of the 2026-08-26 `/ship-prod`. So there
is **no case of a `[x]` batch whose code is missing**. The gaps below are the three other shapes
the task asked for: checked-off-but-not-fully-closed, contract promises not yet reconciled with a
shipped decision, and launch gates left open.

- **FEAT-A01 (HIGH) — Launch gate L5 is the only phase never closed.**
  `docs/LAUNCH_PLAN.md:30` and `:414-436`. Seven sub-items are unchecked: confirm account
  creation/login, confirm the Monday-Saturday slate refresh and Saturday reminder, watch the
  14:30 lock and settlement retries, confirm standings/combined coupon post-settlement, review
  errors/failed pushes/DB connections, confirm staging is dormant, and record launch results
  separately from the batch log. Notably, real play has already happened in production (2-1 Hibs
  has played rounds since 8 August per the Batch 68/74 backfill narrative,
  `BUILD_PLAN.md:2032-2069` and `:2248-2281`), so the underlying events L5 asks to "watch" have
  occurred — the gate document itself is what has not been walked and ticked via
  `/launch-closeout L5`.

- **FEAT-A02 (HIGH) — No managed backup or PITR; explicitly the largest standing risk.**
  `docs/LAUNCH_PLAN.md:183-192` (open `[ ]`, deferred by owner 2026-07-30) and reaffirmed at
  `STATUS.md:1115-1118`: "Production still has no managed backup and no PITR... This remains the
  largest standing risk and it needs an owner decision before it needs any code." Batch 75
  (`BUILD_PLAN.md:2283-2324`) only removed a nightly dump that was never durable in the first
  place (`/tmp`, no volume) — it explicitly states it is "not the fix for the egress restriction"
  and changes nothing about recoverability. `picks.odds_at_pick`, `points_awarded`, and `status`
  — the entire scored history of the game — have zero second copy today.

- **FEAT-A03 (MED) — Rate-limit counters still live in process memory.**
  `docs/LAUNCH_PLAN.md:127-134`, open `[ ]`. "Accepted for launch, not fixed": a Railway restart
  clears every IP-keyed counter (login attempts, `pin/reset-request`, provider-budget limits).
  The durable per-profile PIN lockout in Postgres backstops the worst case, but every other
  IP-keyed limit resets silently on redeploy — and this codebase redeploys often (dozens of
  `/ship-prod` runs are named in `STATUS.md`).

- **FEAT-A04 (LOW) — Migration-on-boot still runs inside the web process.**
  `docs/LAUNCH_PLAN.md:193-197`, open `[ ]`. Not urgent while `railway.toml` pins
  `numReplicas = 1`, but it is a standing precondition nobody has scheduled work against; the
  note exists "so nobody raises the replica count without reading it."

- **FEAT-A05 (MED) — The "private" product contract is undercut by two shipped defaults, and
  the tension was recorded but never re-closed.** `AGENTS.md:5` and `BUILD_PLAN.md:5` both open
  with "The Coupon is a private weekly football accumulator game." Batch 63
  (`BUILD_PLAN.md:1771-1833`) made account creation fully open and unauthenticated — no invite,
  no join code — and its own scope note (`BUILD_PLAN.md:1827-1833`) records the consequence
  verbatim: "a league whose `privacy` is `public_request` or `public_open` is discoverable and
  joinable... changed from 'members the operator provisioned' to 'anyone with an account'... left
  for the owner." Production's `test` league is `public_open` and was deliberately left that way
  on 2026-08-20 (`BUILD_PLAN.md:1831-1833`). No later batch revisits whether that combination
  (open signup + open league defaults, see FEAT-B02) still matches the one-line product premise.

- **FEAT-A06 (LOW) — BUILD_PLAN.md's own "Architecture" section is stale against Batch 46.**
  `BUILD_PLAN.md:35-41` still describes `FootballDataProvider` as "live as `ApiFootballProvider`,"
  but Batch 46 (`BUILD_PLAN.md:1066-1171`) shipped `FotMobProvider` as the actual production
  implementation (`FOOTBALL_DATA_PROVIDER=fotmob`) with `ApiFootballProvider` demoted to an
  alternate the free plan can no longer serve current-season data on. ADR 0007 supersedes ADR
  0003's provider choice per the batch text, but the top-of-document architecture summary — the
  section this task was told to check for "a promise made but not batched" — was never amended to
  match, so a reader of just that section learns the wrong provider is canonical.

- **FEAT-A07 (LOW) — FotMob terms-of-service risk is accepted with no monitoring/contingency
  batch, despite now backing three live features.** Batch 46 (`BUILD_PLAN.md:1141-1146`) records:
  "FotMob's terms prohibit automated access. The owner took that decision knowingly... recording
  it as a decision is the point: it stays revisitable." It now underpins Football Stats (Batch
  46/51), the void-fixture cross-check that removes phantom fixtures before lock (Batch 64), and
  live in-play scores (Batch 72) — three shipped, member-facing features resting on an
  unsupported dependency, with TheSportsDB named as "the fallback if the terms or the fragility...
  turn out to bite" but no batch or launch item tracking for that trigger.

- **FEAT-A08 (LOW) — Three renamed members were never told, and their old names are now
  registrable by anyone.** `STATUS.md:1082-1086`: Batch 74 renamed Craig, Birch and Lewis to
  their full names for sign-in purposes; nobody was signed out (JWT subject is the player id), so
  the failure surfaces "days later looking unrelated" at next PIN reset/session expiry, and the
  freed short names are now open to registration by a stranger. This sits in STATUS.md prose as
  an open action item, not as a tracked batch or gate.

- **FEAT-A09 (LOW, informational) — Unknown Supabase egress-quota consumer.**
  `STATUS.md:1120-1121`: "still unknown... the consumer may not be this project at all." Batch 75
  explicitly disclaims being the fix. Per prior incident memory this already produced a
  production 402 (`exceed_egress_quota`) with avatar storage down while Postgres kept answering,
  so this is a live recurrence risk without an owner, not just a curiosity.

---

## Part B — Independent product judgment

Checked directly against the routers and web source rather than inferred from the build log.
Several things the task asked to verify turned out to be solidly built already — noted below so
they aren't mistakenly re-flagged: **kicking a member** (`DELETE
/api/v1/leagues/{slug}/members/{target_player_id}`, `apps/api/src/routers/league_memberships.py:271-299`,
wired to a confirm-by-typing-the-name dialog in `apps/web/src/pages/LeagueMembersPage.tsx:69-80,189-206`),
**onboarding empty states** (`EmptyState` used throughout `CouponPickPage.tsx`, `ResultsPage.tsx`,
etc., and Batch 47 made a brand-new league's first round appear instantly rather than the next
morning), and **account recovery when a device is also lost** (auth has no device binding at all
— any device logs in with display name + PIN — so losing a device alone is a non-issue, and losing
the PIN too routes through the built admin-reset flow, Batch 66, `apps/api/src/routers/admin.py:175-230`).

- **FEAT-B01 (HIGH) — The one action the whole game is built around has no offline handling.**
  `apps/web/src/hooks/usePickEditor.ts:67-86` is a bare TanStack `useMutation` around
  `POST .../picks`: no retry, no offline detection, no queued/background-sync submission. A
  failed request — weak signal in a pub on a Saturday afternoon, the exact moment this app is
  used hardest — surfaces only as the generic toast `pickErrorMessage`'s default branch,
  "Could not save your pick — try again" (`usePickEditor.ts:42`), indistinguishable from a real
  409 conflict. The member has no way to tell whether their claim landed before someone else took
  the selection. Contrast with reads: `apps/web/src/sw.ts:26-49` gives every `GET /api/v1/*` a
  resilient Workbox `NetworkFirst` cache with a 3-second timeout and an offline fallback. Because
  odds freeze at submission and picks are a first-come land-grab (the product's own framing, per
  Batch 76's copy "Dave took Arsenal... before someone else does"), this is the single highest-
  value place for offline resilience in the app, and it currently has none.

- **FEAT-B02 (MED) — New leagues default to fully open, with no explanation, in a product whose
  premise is private.** `apps/web/src/pages/CreateLeaguePage.tsx:24` initialises
  `privacy = 'public_open'` ("Open — anyone can join instantly"); the `<select>` at
  `CreateLeaguePage.tsx:118-123` carries no copy explaining what that now means given Batch 63
  made account creation open to anyone. A friend spinning up "our Saturday crew" who does not
  touch the privacy dropdown gets a league any stranger with a self-registered account can join
  instantly — the least-private option is the default, in a product whose one-line description
  (`AGENTS.md:5`) is "private." Pairs with FEAT-A05.

- **FEAT-B03 (MED) — No season boundary anywhere in scoring, so there is no season-to-season or
  league-vs-league comparison.** `standings_by_league`
  (`apps/api/src/services/scoring.py:418-460`) aggregates every settled pick a league has ever
  played, unbounded by date, despite its own docstring calling the result "Season tables."
  Gameweek *numbering* does reset per season internally
  (`season_bounds`/`next_gameweek_number`, `apps/api/src/services/gameweek.py:66-94`) but the
  leaderboard never does — a league that runs three years reads as one never-ending table with no
  "this season" view and no archive of a past one. Beyond a member's own cross-league career
  rollup (`apps/web/src/pages/CareerProfilePage.tsx`), there is also no screen that compares two
  leagues side by side (e.g. which of a member's leagues is more competitive, has tighter odds,
  bigger roster).

- **FEAT-B04 (MED) — League admins have no visibility into their own league's audit trail.**
  `AuditLog` rows are written for league-level admin actions (promote/demote/remove a member,
  settings changes — e.g. `apps/api/src/routers/leagues.py:484-490`,
  `league_memberships.py`), but the only reader anywhere in the API is the site-admin-only
  `GET /api/v1/admin/dashboard` (`apps/api/src/routers/admin.py:660-668`), capped at
  `RECENT_AUDIT_ROWS = 25` (`admin.py:523`), global across every league in the deployment, with
  no filter and no pagination. In this product a league "admin" is typically just the friend who
  set the league up, not the site operator — and that person cannot see who changed the fixture
  window, who was removed, or when, inside their own league. The site console (Batch 66/69) is
  strong; the per-league equivalent for an ordinary league owner does not exist.

- **FEAT-B05 (LOW) — No search or filter over round/member history.**
  `apps/web/src/pages/ResultsPage.tsx` (the "Season" tab) lists every settled gameweek
  chronologically with no search box, date filter, or pagination (full file is 154 lines, plain
  `.map()` over the result list); `LeaderboardPage.tsx` has no name search or column sort. Low
  impact at today's 15-50-member, effectively single-season scale, but combines with FEAT-B03 (no
  season reset) so the list only grows and never gets a natural break point.

- **FEAT-B06 (LOW) — Sharing stops at the pre-lock coupon; a settled result or standing can't be
  shared out.** Batch 24 built copy-to-clipboard for the combined coupon before settlement
  (`CombinedAccaView.tsx`), and it's the only such surface — a `grep` for clipboard/share usage
  across `apps/web/src` returns only that view, the league-invite page, and the welcome page.
  There is no equivalent for "we hit 5/6 this week" or a season rank, the two moments members are
  most likely to want to brag about outside the app; today that requires a screenshot.

- **FEAT-B07 (informational, not a gap) — Account recovery beyond PIN reset was checked and is
  fine.** Auth has no device binding (`routers/auth.py`): any device can log in with display name
  + PIN, so losing a device alone is not a recovery scenario. Losing the PIN as well routes
  through the built admin-reset flow (Batch 66) which clears the credential for set-on-next-login
  rather than minting a shareable temporary one. Recorded here only because the task asked it be
  checked explicitly.

---

## Counts

- **Part A:** 9 findings (FEAT-A01–A09) — 2 HIGH, 3 MED, 4 LOW.
- **Part B:** 6 findings (FEAT-B01–B06) — 1 HIGH, 3 MED, 2 LOW — plus one informational
  non-finding (FEAT-B07) recorded to show it was checked.
