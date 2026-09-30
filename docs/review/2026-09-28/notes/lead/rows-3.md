- [ ] **Batch 189 — The discovery budget prices the wrong number, and the match-day refresh has no budget**
  — specified from `docs/review/2026-09-28/02-correctness.md` CORR-24 and
  `04-performance-operations.md` PERF-21 (MED, live, verified; CORR-15 partial). Batch 133
  charges each discovery walk `len(set(competition_ids))` (`gameweek.py:1065`), but the job
  passes the *raw* pool (`scheduler.py:508-522`; the helper's docstring says the caller
  intersects), while `fetch_slate` walks only the played intersection — 36 charged, 23 walked
  at the repo's own 27 Sep measurement. So at two windows the run stops at half its budget and
  never pre-discovers week two; at three the last window is not served. `run_refresh_slate`
  (`scheduler.py:578-586`) passes no budget at all: 23 requests per window per run, 118 in each
  of the 09:00 and 11:00 hours at five windows, and a 429 there holds the pick path for five
  minutes.

  Price each walk at the competitions that will actually be walked, and give the refresh the
  same budget (or a share of one hourly budget between the two).

  Verification: with a counting fake at production's pool shape (36 raw / 23 played), the
  daily run serves every window at one, two and three windows inside its budget; the refresh
  stays inside 100/hour at five windows; Batch 119's per-(window, date) commit rule unchanged.

  Scope boundary: the two jobs' costing. **API-carrying.**

- [ ] **Batch 190 — One pick bucket for the whole deployment refuses picks the plan could afford**
  — specified from `docs/review/2026-09-28/04-performance-operations.md`, PERF-23 (MED, live,
  verified hourly). Batch 161's installation bucket and the per-league one are both
  `50/hour;100/day` (`routers/picks.py:118, 138`) and count submissions, including a changed
  mind, not provider requests. However many leagues there are, 50 submissions an hour get
  through in total, and 100 a day — while a measured one-window Saturday spends 289 of 500.
  Two 25-member leagues sharing a 14:30 lock reach the hourly ceiling. Not reachable at
  today's 13 members.

  Charge the installation bucket only when the pick path actually goes upstream (the cache
  knows whether the 60-second price was a hit), and size its day from what the measured day
  leaves spare.

  Verification: two leagues × 30 members picking in one hour, most from a warm cache, all
  admitted; a cold-cache burst still bounded by the plan; `PICKS_BUSY` message unchanged.

  Scope boundary: what the installation bucket counts. **API-carrying.**

- [ ] **Batch 191 — A burst of picks in a big league exhausts the database pool and silently drops the alerts**
  — specified from `docs/review/2026-09-28/04-performance-operations.md`, PERF-20 (MED, live,
  verified). Batch 162 moved the pick alert after the response into `_announce_after_response`
  (`routers/picks.py:492-553`), which holds one pooled connection across every send (~9 s at 50
  members). Batch 146 sized the pool at 5 + 5. Twelve members of a 50-member league submitting
  at once: 10 answered 201, 2 answered 500 after 10 s (`QueuePool limit … timed out`), and 6 of
  the 10 fan-outs died acquiring a connection outside the wrapper that swallows failures — 294
  alerts never sent, nothing retries them. Two batches, each green on its own, combine into it.

  Read recipients and subscriptions up front, release the connection, send without a session,
  record delivery in a short second transaction; bound concurrent fan-outs below the pool
  size; catch failures for the whole background task.

  Verification: the lens's burst (12 simultaneous in the 50-member league, sends stubbed at
  179 ms) — every pick 201, every eligible member alerted exactly once, the pool never
  exhausted; Batch 107's completion retry unchanged.

  Scope boundary: the pick fan-out's connection use. **API-carrying.**

- [ ] **Batch 192 — The pick screen makes two queries per competition**
  — specified from `docs/review/2026-09-28/04-performance-operations.md`, PERF-18 (MED, live,
  verified). `fixture_context` calls `resolve_names` once per competition
  (`football_data.py:945-952`), each reading aliases then teams: 10 + 2 × competitions
  statements — 56 at production's 23. Its docstring claims "three queries for a slate of any
  size". The 2026-09-13 review's "no N+1 anywhere" missed it because its round spanned one
  competition.

  Resolve every competition's names in two `IN` queries and make the docstring true.

  Verification: the round's statement count flat across 1, 23 and 41 competitions; resolved
  names identical.

  Scope boundary: name resolution on the slate. **API-carrying.**

- [ ] **Batch 193 — A scheduled job that fires while the worker is busy is dropped**
  — specified from `docs/review/2026-09-28/04-performance-operations.md`, OPS-17 (MED) and
  OPS-18 (LOW), carried from 2026-09-13 with no batch. All 13 registered jobs take APScheduler's
  one-second `misfire_grace_time` (only the switched-off backup sets 3,600); re-driven, a real
  job due during a 1.5 s busy loop was dropped. Every Saturday hour `lock_gameweeks` and
  `live_scores` share :00 with discovery, the warm pass, the refresh and settlement at several
  hours.

  Set `misfire_grace_time` and `coalesce=True` on every job, sized to its cadence, and stagger
  the ones that share the top of the hour where their order does not matter.

  Verification: a test that each registered job carries a grace time; the busy-loop reproduction
  runs the job late instead of dropping it; the lock sweep still runs before settlement.

  Scope boundary: job registration. **API-carrying.**

- [ ] **Batch 194 — Half the league never hears what the app announces**
  — specified from `docs/review/2026-09-28/05-feature-gaps.md`, FEAT-B10 (MED; absence
  verified, reach plausible) and FEAT-B11 (LOW). Five member-facing push types exist (picks
  open, reminder, pick made, all picked, round settled), all fire-and-forget: no message table,
  no inbox, no screen. STATUS records 7 push subscriptions for 13 active accounts, and on iPhone
  push needs the installed app, so about half the league gets none of them. Mute is per league
  or nothing, not per kind.

  **Owner decision** (README decision 9; recommended: build it). Record each league
  notification per member when sent (a small table, 30 days), show it behind a bell on home,
  mark read on view; per-kind mute if cheap alongside.

  Verification: a member with no subscription sees each event in the app; read state
  persists; muted kinds are neither pushed nor listed; retention prunes at 30 days.

  Scope boundary: notification history. **Migration + API + web — a migrating shipment needs
  its recovery note (Batch 128).**

- [ ] **Batch 195 — With sign-ups closed nobody new can get in, and the screen says otherwise**
  — specified from `docs/review/2026-09-28/05-feature-gaps.md`, FEAT-A12 (LOW, carried, sharper).
  The register screen does not know the kill switch; with it off a visitor fills the form and
  only then learns "Ask a league admin for an invite" — but claiming an invite needs an account
  and nothing creates one, so there is no way in at all. The switch's state is already public
  (registration checks it before validating the name, `auth.py:426`).

  **Owner decision** (README decision 10; recommended: a separate unauthenticated
  `GET /api/v1/auth/signup-status`, leaving `/config` authenticated). Show a closed notice in
  place of the form, and either let an invite create an account while sign-ups are closed or
  stop telling visitors to ask for one.

  Verification: sign-ups closed → the notice, no form; an invite path that works or no promise
  of one; sign-ups open → unchanged.

  Scope boundary: the closed-sign-up journey. **API + web.**

- [ ] **Batch 196 — The results history ignores the season, and members cannot share the join code they hold**
  — specified from `docs/review/2026-09-28/05-feature-gaps.md`, FEAT-B09 (LOW, carried) and
  FEAT-B12 (LOW). `/results` lists rounds from both seasons and ignores `?season=` while
  standings split correctly. Every member receives the league's join code from the API but only
  admins have a screen to share it.

  Honour `?season=` on results and add the season selector the leaderboard has; a share action
  for the join code on the league screen for members of leagues that allow it.

  Verification: results across a season boundary filter correctly; a member can copy/share the
  code in a league whose privacy permits joining by code, and not in one that does not.

  Scope boundary: these two. **API + web.**

- [ ] **Batch 197 — An invite link does not say who is inviting you to what**
  — specified from `docs/review/2026-09-28/06-premium-design.md`, DES-23 (low). `/join/:token`
  lands on "Join the league" without naming the league or the inviter.

  **Owner decision** (README decision 12; recommended: league name, inviter's display name and
  member count). A public read keyed by the invite token, and the landing page using it.

  Verification: a live invite shows the three facts; an expired, used or deleted-league invite
  shows the existing refusal; the read leaks nothing without a valid token.

  Scope boundary: the invite landing. **API + web.**
