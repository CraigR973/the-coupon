- [ ] **Batch 179 — A league admin can take over any member of their league, and every other league that member plays in**
  — specified from `docs/review/2026-09-28/01-security.md` (SEC-15 partial, SEC-27 MED) and
  the lead's SEC-32 (HIGH, live, verified; `10-reconciliation.md`). Batch 122 refuses a
  league-scoped reset only when the target is a site admin or a *current* league admin.
  Everyone else is unchanged: a league admin clears the PIN and for 24 hours the
  unauthenticated `/auth/pin/set` accepts a new PIN for that name from anyone. Reproduced to a
  signed-in session as an ordinary member (Carol) and as a co-admin demoted first (SEC-27:
  demote → reset → set → login). The session is the victim's whole account, so the attacker
  also acts in the victim's *other* leagues, where they hold no role. The victim is told
  nothing (`credentials.clear_pin` sends no notice) and is simply signed out. The guard's own
  comment (`league_memberships.py:625-628`) states the invariant it misses: no league admin
  may open the window "on an account whose privileges reach beyond an ordinary membership in
  this league". No web screen calls this route (05, FEAT-A15), yet the register screen tells a
  member "a league admin has to set you a new one".

  **Owner decision first** (README decision 1). Recommended: retire the league-scoped reset
  route so every reset goes through the site console the owner already uses, correct the
  register screen's copy, and notify the member (push, plus an in-app notice on next sign-in)
  when a reset is issued and when a PIN is set. The alternative (01's options 2 + 4) keeps the
  route for members in no other league, refuses it for anyone demoted inside the claim window,
  and notifies.

  Verification: a test that a league admin cannot clear an ordinary member's PIN (or, on the
  alternative, cannot clear a member of another league or anyone demoted inside the window);
  a test that the member is notified on reset and on set; the site-console reset and its
  audit unchanged; the register copy names a path that exists.

  Scope boundary: the league-scoped reset and reset notifications. No change to the claim
  window or the site console. **API + web (copy only; safe before the API ships).**

- [ ] **Batch 180 — One address can still lock any number of members out of sign-in**
  — specified from `docs/review/2026-09-28/01-security.md`, SEC-28 (MED, live, verified; SEC-18
  partial). Batch 123's per-source budget (15 wrong PINs per 15 minutes) is charged by a
  callable the handler invokes only after the wrong PIN has been counted, the account locked
  and the transaction committed (`routers/auth.py:329-344`, `rate_limit.py:330-351`); nothing
  consults it first. From one address, five members were locked; the fourth and fifth got 429
  and were locked anyway. The batch's test asserts only that some 429 appeared
  (`tests/test_durable_rate_limit.py:443-463`).

  Peek at the source bucket before verifying the PIN and refuse with 429 when it is spent;
  keep charging only on failure, so a correct sign-in from a shared address costs nothing.

  Verification: a test that after the source budget is spent the next victim's
  `failed_login_count` and `locked_until` are unchanged; a test that a correct PIN from that
  address still signs in; the per-(name, address) limit and the account lock unchanged.

  Scope boundary: the login source limit. No change to the account lock. **API-carrying.**

- [ ] **Batch 181 — A per-league name can copy someone outside the league, and no screen sets one**
  — specified from `docs/review/2026-09-28/01-security.md` SEC-29 (LOW-MED, live, verified) and
  `05-feature-gaps.md` FEAT-A15 (LOW). Batch 126 checks an override only against the league's
  *current* members (`league_memberships.py:364-390`); nothing re-checks on join. Bob took the
  name "Erin" (in another league) and "Sam" (the site admin's); Erin then joined and the roster
  showed two "Erin"s. The route has no web caller at all.

  **Owner decision** (README decision 5). Recommended: remove the per-league name route and its
  override column's writers, since nothing in the app uses it. Otherwise: check global display
  names of all profiles when an override is set, and on every join path refuse or clear an
  override that now collides.

  Verification: on removal, the route 404s and existing overrides are cleared by a data step
  with a count; otherwise, tests for both collision directions (set-then-join, join-then-set).

  Scope boundary: the per-league name. **API-carrying.**

- [ ] **Batch 182 — Input bounds and policy hygiene**
  — specified from `docs/review/2026-09-28/01-security.md`, SEC-31 (LOW) and the CSP notes
  (INFO). `display_name_hint` on league invites has no `max_length` against a `String(100)`
  column, so a 150-character hint is a 500 (`league_memberships.py:438`); a league
  `description` is unbounded. Production's web CSP allows the *staging* API in `connect-src`
  and any `*.supabase.co` in `img-src`, because one `vercel.json` serves both environments.
  `config.py:113-114`'s comment says the manual allowance brings the budget to "460 of 500";
  it is 481.

  `Field(max_length=100)` on the hint and a bound (500) on the description; split the CSP per
  environment and narrow `img-src` to the project's storage host; correct the comment.

  Verification: 150-character hint → 422; production headers after the push carry only the
  production API; the prod-bundle CSP smoke still passes.

  Scope boundary: these bounds, the CSP and one comment. **API + web.**

- [ ] **Batch 183 — A big league's home screen and results history break once the accumulator passes 10^26**
  — specified from `docs/review/2026-09-28/04-performance-operations.md`, PERF-19 (HIGH, live,
  verified by the lens and re-run by the lead). `combined_odds` (`services/coupon.py:30-40`)
  quantizes the product to 2 dp under Python's default 28-digit context; at about 10^26 it
  raises `decimal.InvalidOperation`, uncaught at all four call sites (home summary
  `me.py:469, :552`, coupon `coupon.py:179`, results `scoring.py:773`). 30 legs fail at an
  average price of 7.36, 40 at 4.47, 50 at 3.32; `max_members` allows 50. At the stress shape
  the home summary and results returned 500 for every member of the big league — permanently
  for results, since history does not change. Not reachable at today's 13 members.

  Quantize inside `decimal.localcontext()` with enough precision, and decide how an absurd
  price displays (full, or capped with a marker) — the share text too.

  Verification: a 50-leg test at realistic prices through all four call sites; the home
  summary and results return 200 at the stress shape; existing coupon tests unchanged.

  Scope boundary: the combined-odds arithmetic and its display. **API-carrying — first in its
  group.**

- [ ] **Batch 184 — After a window change, a round that can never settle still takes picks, and shares a label**
  — specified from `docs/review/2026-09-28/02-correctness.md`, CORR-20 (MED, live, verified)
  and CORR-13 (MED, carried — not fixed by Batch 121). Batch 121's settle guard
  (`scoring._same_week_round_may_settle`) is right about scoring, but nothing on the offering
  side knows it: discovery still creates the round, the list shows it, and the pick path checks
  only status and time. Reproduced two ways — a kept stray Saturday round accepted a new pick
  after a Saturday→Friday edit; a Friday league moved to Saturday after its week settled got a
  new Saturday round, labelled like the settled one, that both members picked — and both rounds
  are refused at every settle sweep for ever, their picks pending, with no member told. Both
  rounds in one football week still render the same bare label.

  **Owner decision** on picks already stranded (README decision 3; recommended: void them).
  Then: `sync_slate` does not create a round in a football week where the league already holds
  a settled round or a kept stray; the pick path refuses (`409 ROUND_NOT_SCORING`) any round the
  guard would refuse; an operator path voids a refused round's picks; the second round in a
  week takes a distinct label.

  Verification: both reproductions leave no pickable non-scoring round and one label per week;
  an already-stranded round's picks void with one audit row and a settle notification; Batch
  112 and 121's tests unchanged.

  Scope boundary: round offering, the pick refusal, the void path, the label. No change to
  scoring. **API-carrying.**

- [ ] **Batch 185 — A member who leaves or deletes their account keeps blocking the round they walked away from**
  — specified from `docs/review/2026-09-28/02-correctness.md`, CORR-19 (MED) and CORR-27 (LOW),
  live, verified. Self-service deletion (`me.py:625`, Batch 136) never calls
  `settle_completion_after_roster_change`, which leave, remove and site-admin delete all call
  (Batch 130): when the last outstanding picker deletes their account the round completes
  silently and the next pick change is announced as the completing pick. Separately, a
  departed member's pick on a round that has not locked stays claimed, so that selection or
  fixture is unavailable to everyone else all week.

  **Owner decision** on unlocked picks (README decision 2; recommended: delete them on leave
  and on erasure, keep locked and settled ones — the 2026-09-22 "keep history" decision was
  about history, and an unlocked pick is not history yet). Then call the completion hook from
  `delete_my_account` for each of the member's leagues.

  Verification: mirror Batch 130's leave test for self-deletion; a departed member's unlocked
  claim released and claimable by another member; locked and settled picks kept and still
  summing into standings.

  Scope boundary: roster exits. **API-carrying.**

- [ ] **Batch 186 — The same week's accumulator shows two different prices**
  — specified from `docs/review/2026-09-28/02-correctness.md`, CORR-21 (LOW, live, verified;
  void-leg decision partial). Batch 156 excluded void legs in `build_coupon` only; the Results
  list (`scoring.py:773`) and home's "Last result" (`me.py:469, :552`) still multiply them —
  54.91 there against 7.44 on the coupon for the same round, and home says "4-fold".

  Filter void legs through one shared helper at every call site and carry `void_leg_count` on
  `GameweekResult` and `LastResult`; the web's two readers adjust the fold count.

  Verification: one round with two void legs reads the same price and fold count on the
  coupon, results and home; the web reads the new field as optional so it is safe before the
  API ships.

  Scope boundary: the three combined-odds call sites. **API + web.**

- [ ] **Batch 187 — A wrong result can only be fixed pick by pick, from curl, with a database read, and nobody is told**
  — specified from `docs/review/2026-09-28/05-feature-gaps.md` FEAT-A13 (MED) and FEAT-A14
  (LOW), and `02-correctness.md` CORR-22 and CORR-23 (LOW), all live and verified. Batch 134's
  correction (`POST /admin/picks/{id}/correct`) scores correctly but has no screen, and no read
  available to a site admin returns another member's pick id (0 of 17), so using it needs a
  production database read. It corrects one pick: after fixing Bob's Draw to 1-1, Alice's
  Arsenal pick on the same fixture still read "won 19". The corrected member is never told;
  neither the correction nor a hand settlement appears in the league's audit log; and a round
  nobody picked never settles, so it is never announced.

  **Owner decision** on scope (README decision 4; recommended: per fixture across leagues).
  Then: a site-admin action on the admin Results screen — pick a settled fixture, enter the
  true score or void and a reason — re-scoring every settled pick on it in every league through
  `resolve_pick`; one audit row per league carrying `league_slug`; a `corrected` flag and
  reason on each pick; the member's settle line re-sent when their result changes; a locked
  round with no picks flips to settled after its window and is announced.

  Verification: a fixture correction consistent across two leagues' standings, coupons,
  results and career numbers; idempotent; audited per league and visible in each league's log;
  one notification per changed member; a no-pick round settles once.

  Scope boundary: correcting settled fixtures and settling empty rounds. **API + web.
  Rewrites awarded points.**

- [ ] **Batch 188 — Running the season-calendar backfill could renumber every league by one week**
  — specified from `docs/review/2026-09-28/02-correctness.md`, CORR-25 (LOW, verified on a
  scratch database). `backfill_season_calendar.plan` joins `leagues` with no `deleted_at`
  filter (`:61-65`), and the runtime re-anchor reads `gameweeks` the same way, so one early
  round in a deleted or test league moves week 1 and shifts every live round's label; the dry
  run never names the row that set the anchor. The owner has not run the backfill yet
  (STATUS, "Waiting on the owner").

  Filter deleted leagues in `plan`, `reanchor_from_earliest_round` and
  `ensure_calendar_for_new_season`, and print the round that set each anchor in the dry run.

  Verification: the lens's scratch reproduction (a deleted league with a 1 Aug round) leaves
  the anchor on the first live Saturday; the dry run names the anchoring round.

  Scope boundary: those three reads and the dry-run output. **API-carrying — ship before the
  owner runs the backfill.**
