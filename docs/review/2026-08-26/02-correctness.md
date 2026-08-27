# 02 — Correctness (follow-up review)

Reviewed at `3795854` (Batches 79-81 shipped, 79 commits since `308bc16`) against
the code only — no running server this time; every finding below is a read of the
actual source, cited by `file:line`, cross-checked against the test suite that
covers it. Continues `docs/review/2026-08-22/02-correctness.md`; CORR-01 through
CORR-03 are unrevisited (already fixed, out of scope). CORR-04 and CORR-05 are
re-examined per the brief below; new findings from the 79 commits since are
numbered from CORR-06.

## Re-examining CORR-04 and CORR-05

### CORR-04 · was LOW, "reachability unconfirmed" · now **resolved — the review's own concern does not hold**

The 2026-08-22 review flagged that a mid-round `pick_scope` change would leave
already-written rows outside the new scope's partial unique index. That concern
is answered by `_apply_pick_scope_change` at
`apps/api/src/routers/leagues.py:501-530`, called from `update_league` at
`apps/api/src/routers/leagues.py:1004-1007`. It:

- restamps every `pending` pick in the league onto the new `pick_scope`
  (`leagues.py:526-530`), so old rows are not exempted from the rule the league
  just adopted;
- refuses to tighten to `fixture` scope at all when two members already hold
  different selections on the same fixture, with `409 PICK_SCOPE_CONFLICT`
  (`leagues.py:513-524`), rather than silently creating an unenforceable state.

**This function is not new.** `git log -S"_apply_pick_scope_change"` dates it to
`329daa6` (Batch 10), and it was present, byte-for-byte, in `apps/api/src/routers/leagues.py`
at `308bc16` — the exact commit the 2026-08-22 review was reviewing. The review
raised CORR-04 without finding this function, which already closed the gap it
describes. It is thoroughly tested: `apps/api/tests/test_picks_flow.py:727-805`
covers the refusal-on-conflict path and the restamp-of-pending-picks path over
HTTP, including reading the restamped `pick_scope` back off the rows.

No new code since `308bc16` touches this path. **Correction to the register: CORR-04
should never have been left open — the mechanism it worried about already existed
at review time.**

### CORR-05 · LOW, "no league configuration in play" · **still open, and now more reachable**

The underlying arithmetic is unchanged: `apps/api/src/services/odds_provider.py:264-273`
still builds local instants as `datetime(y, m, d, tzinfo=UK_TZ) + timedelta(minutes=...)`,
which is correct under `zoneinfo` everywhere except the DST transition hour itself,
where a non-existent or ambiguous wall time silently resolves via `fold=0` rather
than raising.

What has changed since the review is **who can reach it**, not the code:

- The capability to configure a window landing at 01:00–02:00 on the DST-transition
  Sunday already existed at `308bc16` — `League.slate_start_minute`/`slate_start_weekday`
  accept any minute (0-1439) on any weekday (`apps/api/src/models/league.py:146-157`),
  with no validation excluding the transition hours anywhere in
  `apps/api/src/routers/leagues.py`, and the settings screen exposes it as an
  ordinary `<input type="time">` plus a weekday `<select>`
  (`apps/web/src/pages/LeagueSettingsPage.tsx:394-440`) — no server or client
  validation stops a Sunday 01:00 window. This UI and the underlying columns
  predate the review (Batch 15, `4cb6267`).
- `create_league` (`apps/api/src/routers/leagues.py:612-654`) requires only
  `CurrentUser` — no role or admin check — so **any authenticated player** can
  create a league with an arbitrary window.
- Batch 63 (`fbb0403`, shipped the same day as the review) added
  `POST /api/v1/auth/register`, open self-serve account creation with
  `public_signup_enabled` defaulting to `True`
  (`apps/api/src/config.py:225`, `apps/api/src/routers/auth.py:386-394`). Before
  that batch, accounts were owner-provisioned only (`docs/adr/0001-...md`,
  superseded by `docs/adr/0008-...md`), so only people the owner had already
  vetted could reach `create_league` at all.

Put together: the review's "no league configuration in play" reasoning was about
the leagues actually configured on 2026-08-22, not about who could configure one.
Since Batch 63, literally anyone with the app's URL can register, then create a
league landing its window on the DST-transition hour, with no gate in between. The
severity judgement (LOW) still seems right — it requires deliberately picking an
unusual time, the blast radius is one league's own lock/opening instant rather
than a shared resource, and `fold=0` fails safe (resolves to a definite instant
rather than crashing) — but "no league configuration in play" is no longer an
accurate reason to leave it unfixed, since Batch 63 removed the vetting step that
statement was implicitly leaning on.

**Suggested fix (unchanged in spirit from the original finding):** reject window/lock
configurations at `_check_claim_period` / the `UpdateLeagueRequest`/`CreateLeagueRequest`
validators in `apps/api/src/routers/leagues.py` when the computed local instant would
fall in the DST-transition hour, or store/derive lock and window instants without
reconstructing local wall time at all.

## New findings since `308bc16`

## CORR-06 · MED · Public registration's case-insensitive uniqueness has a case-sensitive backstop

`apps/api/src/routers/auth.py:429-469` pre-checks display-name uniqueness
case-insensitively (`func.lower(Profile.display_name) == name.lower()`,
`auth.py:436`) specifically because, per the docstring at `auth.py:429-434`, two
names differing only by case are "one person twice" on a leaderboard — "precisely
the impersonation a public signup invites." The comment at `auth.py:461-463`
claims `uq_profiles_display_name` is "the backstop for the check above losing a
race."

That backstop is `sa.UniqueConstraint("display_name", name="uq_profiles_display_name")`
at `migrations/versions/001_baseline.py:103` — a **case-sensitive** constraint on
the literal column, not a functional unique index on `lower(display_name)`.

So the backstop only catches an exact-case race (two concurrent registrations for
`"Dave"`). Two concurrent registrations for `"Dave"` and `"dave"` both read "not
taken" from the pre-check (`auth.py:435-438`), both pass the case-sensitive
constraint at flush (`auth.py:458-459`), and both commit — producing exactly the
duplicate-identity leaderboard entry the pre-check exists to prevent, with no
`IntegrityError` to catch it. This is Batch 63 (self-serve, unauthenticated,
`REGISTER_LIMIT = "5/hour"` per IP) surface, not pre-existing: before it, accounts
were owner-provisioned one at a time, so a genuine concurrent-registration race for
case-variant names was not a live scenario.

The window is narrow — both requests have to land between one process's SELECT
and its COMMIT — but it is exactly the kind of gap `REGISTER_LIMIT` and the other
guards in this endpoint are meant to close, and the fix is cheap: either make the
unique constraint a functional index on `lower(display_name)` (needs a migration),
or take a `pg_advisory_xact_lock` keyed on `name.lower()` before the pre-check.

## CORR-07 · LOW · `notify_member_joined` bypasses the per-league mute it was Batch 76's stated purpose to enforce everywhere

Batch 76's whole rationale (`apps/api/src/services/push_notification_service.py:1-12,
94-109`) is that `send_notification` previously had no `league_id` to check
`notification_muted` against, so a league-scoped alert could not honour a
member's mute of that specific league. It fixed `notify_pick_made`,
`notify_picks_open`, `send_pick_reminders` and the fixture-postponed alert in
`services/gameweek.py:680-697` — all four now pass `league_id`.

`notify_member_joined` (`apps/api/src/services/notification_triggers.py:40-53`)
was not touched. It tells site admins "`{player}` has joined `{league}`" — an
event that is about one specific league, exactly like the four Batch 76 fixed —
but calls `send_notification` without `league_id` (`notification_triggers.py:47-53`).
Both call sites have the league object in scope and simply don't pass its id:
`apps/api/src/routers/league_memberships.py:93` and `:147`, and
`apps/api/src/routers/leagues.py:1466`.

Per `send_notification`'s own docstring (`push_notification_service.py:120-122`),
omitting `league_id` is supposed to mean "this message is not about a league — an
admin alert, say." `notify_member_joined` is exactly the case that docstring
carves out an exception for, but the message content contradicts it: it names the
specific league. A site admin who is also a member of that league and has muted it
still gets the "New member" push. This is a narrower miss than the one Batch 76
fixed (site admins are a small set, and the volume is one push per join rather
than per pick), which is presumably why it wasn't caught, but it's the same class
of bug the batch was written to eliminate.

No test in `apps/api/tests/test_notification_batch_76.py` or anywhere else in the
suite exercises `notify_member_joined`'s mute behaviour — `grep -rn
"notify_member_joined"` over `apps/api/tests/` returns nothing outside the mypy
cache.

**Suggested fix:** give `notify_member_joined` a `league_id: uuid.UUID` parameter
and pass it through at both call sites, matching the other three triggers.

## Verified correct (worth recording, not just skipped)

- **The lock-then-fetch-odds ordering (CORR-02's fix, Batch 57) has not reopened.**
  `apps/api/src/routers/picks.py:144-172` still re-evaluates `pick_refusal` after
  `_snapshot_selection`'s outbound call and before the commit, unchanged in shape
  from the fix, with the same reasoning comment in place.
- **Manual (hand-entered) settlement reuses the one scoring path, not a second
  one.** `apps/api/src/routers/admin.py:946-1008`'s `settle_manually` converts
  admin-entered scores into `EventSettlement` values and hands them to
  `services.scoring.settle_gameweek` unchanged — the same function the scheduler
  calls — so a hand-entered result and a provider result write byte-identical
  `Pick` rows. No duplicate scoring logic exists to drift from the canonical rule.
- **`round(odds × 10)` and the void/loss distinction hold through Batch 80's new
  surface.** `recent_form_by_league` (`apps/api/src/services/scoring.py:359-415`)
  reads `Pick.points_awarded` and `Pick.status` straight off the settled rows
  written by `settle_gameweek` — it does not recompute anything — and keeps `void`
  as its own status distinct from `won`/`lost`, matching `FormRound`'s docstring
  (`scoring.py:250-267`). Confirmed via
  `apps/api/tests/test_leaderboard_form.py:134-153` (void neither wins nor loses,
  stays in the run) and `:219-231` (one league's form never leaks into another).
- **Batch 81's same-day reversal of `with_form`'s default (`False` → `True`,
  `apps/api/src/services/scoring.py:423`) is internally consistent.** The one
  caller that still wants the old behaviour —
  `apps/api/src/routers/me.py:274-281`'s rewound "before this round" table, which
  is differenced against the live table and never rendered — explicitly passes
  `with_form=False`. Grepped every call site of `standings_by_league`
  (`apps/api/src/routers/me.py:260,278`); no caller both wants a rendered table
  and gets a mismatched default.
- **The DST-safety of Batch 65/73's window-close arithmetic.** `apps/api/src/services/gameweek.py:314-356`
  (`_minutes_from_lock_to_window_close`, feeding `current_round_order`'s
  `IN_PLAY_GRACE_MINUTES` bound) computes entirely in integer minutes over
  `locks_at_utc`, a stored UTC instant — it never reconstructs a local wall-clock
  date the way `odds_provider.py:264-273` does, so it does not share CORR-05's
  ambiguity, even though it was written after the review and touches the same
  per-league window columns.
- **The frontend's mirror of `pick_refusal` (Batch 73) agrees with the backend
  case-for-case.** `apps/web/src/lib/coupon.ts:172-178`'s `pickRefusal` checks
  `PICKABLE_STATUSES`, then `picks_open_at_utc`, then `locks_at_utc`, in the same
  order as `apps/api/src/services/gameweek.py:133-138`. This is duplicated logic
  (a client-side reimplementation of a server rule) rather than a single source of
  truth, which is a code-craft note rather than a bug — the two currently agree
  and `apps/web/src/test/*` exercises the mirror directly.
- **Test coverage held up under "tests ship with every batch."** Every new service
  module since `308bc16` without its own dedicated test file
  (`services/admin_ops.py`, `services/credentials.py`,
  `services/football_provider.py`, `services/team_matching.py`) is exercised by an
  existing or sibling test file (`test_admin_operations.py`, `test_request_budget.py`,
  `test_admin_console.py`, `test_auth.py`, `test_avatar.py`, `test_betfair.py`,
  `test_config.py`, `test_odds_session.py`, `test_api_football.py`,
  `test_football_data.py`, `test_football_router.py`, `test_fotmob.py`,
  `test_gameweek.py`, `test_live_scores.py`, `test_migration_014.py`,
  `test_slate_verification.py`, `test_backfill_august_2026.py`, `test_fotmob.py`,
  `test_match_link.py`, `test_picks_flow.py`, `test_team_matching.py`) — the one
  gap found (CORR-07) is a missing case within an existing, otherwise well-tested
  function, not an untested module.
- **The per-league notification mute is enforced belt-and-braces on the three
  high-volume triggers.** `notification_targets`/`members_missing_picks`
  (`apps/api/src/services/gameweek.py:1226-1263`) filter
  `notification_muted.is_(False)` at the query level (`gameweek.py:1296`), *and*
  every one of `notify_pick_made`, `notify_picks_open` and `send_pick_reminders`
  also passes `league_id` into `send_notification`'s own gate
  (`notification_triggers.py:99,134,186`) — so the mute is checked twice on the
  triggers that matter most for volume, and once (missed) on the one that
  doesn't (CORR-07).

## What this review did not do

Not reproduced against a running server or database — no `tests.e2e_server`,
no live HTTP probing, no browser. CORR-06 and CORR-07 are read from the code and
corroborated by grepping the test suite for absence of coverage; neither was
exercised with an actual concurrent-request race or a live push send. `mypy`/`ruff`
were not re-run; nothing in this pass suggested a type-checking gap the pinned gate
wouldn't already catch.

## Register

| id | sev | finding | status |
| --- | --- | --- | --- |
| CORR-04 | ~~LOW~~ | pick_scope change mid-round | **corrected** — mechanism already existed at 308bc16, review error |
| CORR-05 | LOW | DST-boundary local time construction | **open, reachability increased** — Batch 63 removed the vetting step the "unreachable" reasoning leaned on |
| CORR-06 | MED | registration's case-insensitive check has a case-sensitive DB backstop | **open** |
| CORR-07 | LOW | `notify_member_joined` skips the per-league mute gate its own batch was written to add everywhere | **open** |
