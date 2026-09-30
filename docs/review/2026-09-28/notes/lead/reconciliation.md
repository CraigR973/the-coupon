# Lead's reconciliation notes (feeds 10-reconciliation.md)

Each finding re-checked against the source on this branch (code identical to `main`
`eb18bcb`; the review changes only `docs/`). "confirmed" = the cited code says what the
finding says it does.

## 01 — security (checked 29 Sep ~15:05)

| id | checked at | verdict |
| --- | --- | --- |
| SEC-28 | `routers/auth.py:329-344` — lock written and committed at the fifth failure, then `charge_failure()`; `rate_limit.py:330-351` — the charger is a callable invoked only after the PIN check; no pre-check anywhere | confirmed |
| SEC-27 | `league_memberships.py:627-640` — guard reads *current* admin memberships only; demotion route unguarded against a following reset | confirmed (lens reproduction; code agrees) |
| SEC-32 (new, lead) | `league_memberships.py:625-628` comment: "a league admin must never be able to open that window on an account whose privileges reach beyond an ordinary membership in this league"; the check (`:629-640`) considers only admin roles, not memberships of other leagues; `credentials.py:72-95` `clear_pin` sends nothing to the member; `auth.py:791-850` `/auth/pin/set` is unauthenticated for 24 h (`PIN_RESET_CLAIM_WINDOW`) | confirmed — raised to the register by the lead (see below) |
| SEC-29 | `league_memberships.py:364-390` — `_effective_name_taken` scoped to `league_id` and current memberships; no re-check on join | confirmed |
| SEC-30 | OSV output in `notes/01-security/osv.txt`; Batch 127 row says OPS-15 left out | confirmed |
| SEC-31 | `league_memberships.py:438` — `display_name_hint: str | None = None`, no `max_length` | confirmed |

**SEC-32 — why the lead registers it rather than leaving it as an owner decision.** Lens 01
recorded the ordinary-member takeover as an owner decision. The 2026-08-23 decision it
might fall under (Batch 66 row, `BUILD_PLAN.md` ~2195) was taken when only the *site* console
could reset a PIN: it chose "clear, member sets their own" as the mechanism. The
league-scoped reset came later and hands that mechanism to any league admin — and anyone can
create a league. The code's own comment at the guard states the invariant ("privileges
reach beyond an ordinary membership in this league") and the guard does not enforce it for a
member of two leagues. Same-league takeover reproduced by lens 01 (Carol, Hank);
cross-league reach follows from the session being the victim's account (no league scoping
on tokens); the victim is told nothing (`clear_pin`). Rated **HIGH** by the rubric
("credentials exposed under an unusual but reachable condition"), consistent with the
2026-09-13 SEC-15 rating for the same case. Disproof attempted: rate limit 10/hour per admin
(does not prevent a targeted takeover); audit row exists but only the resetting league's
admins can see it; the victim's sessions are revoked, so the victim is signed out rather
than warned. The fix direction and the options remain an owner decision.

## 02 — correctness (checked 29 Sep ~15:10)

| id | checked at | verdict |
| --- | --- | --- |
| CORR-19 | `settle_completion_after_roster_change` called from `league_memberships.py:345`, `leagues.py:1773`, `admin.py:443`; **not** from `me.py:625 delete_my_account` | confirmed |
| CORR-20 | `_same_week_round_may_settle` referenced only in `scoring.py:76, 201`; nothing on the pick or discovery path | confirmed |
| CORR-21 | `scoring.py:773`, `me.py:469`, `me.py:552` pass every leg to `combined_odds`; only `coupon.py` filters void | confirmed |
| CORR-22 | `admin.py correct_pick` — no notification call (lens reproduction) | confirmed |
| CORR-23 | `scoring.py:~292-295` returns `{}` when nothing is pending | confirmed |
| CORR-24 | `scheduler.py:508-522` passes the raw `pooled_competition_ids()` (docstring `gameweek.py:940-958`: "Returns the raw pool. The caller intersects it"); `gameweek.py:1065` `per_walk = len(set(competition_ids))`; `scheduler.py:578-586` refresh passes no `request_budget` | confirmed |
| CORR-25 | `backfill_season_calendar.py:61-65` joins `League` with no `deleted_at` filter; re-anchor `season_calendar.py:~380` reads `min(Gameweek.starts_on)` | confirmed |
| CORR-26 | `CouponSection.tsx:130` — `${legCount} of ${memberCount}` with the current roster | confirmed |
| CORR-27 | erasure and leave keep picks (Batch 136 design); lens reproduction | confirmed |
| CORR-13 | lens reproduction; label derivation unchanged by Batch 121 | confirmed |

## 07 — pipeline (checked 29 Sep ~15:15)

| id | checked at | verdict |
| --- | --- | --- |
| PIPE-10 | `scripts/ci-local.sh:36` runs `"$ROOT/scripts/assert-quality-guardrails.sh"` from the working tree | confirmed |
| PIPE-12 | `gh run list --limit 300` (29 Sep 18:40): 72 runs on `main` since 20 Sep, 8 failures — c7a50bb, a689a57, 48b6627, 0ff3e8c, d1b9ee9, 7ef953d (22 Sep), ac54a71, bf97763 (23 Sep). Note: `gh run list --branch main` silently returns only 16 of them, which first read as 6 failures | confirmed |
| PIPE-11, 13-19 | evidence files in `notes/07-pipeline/`; commit ids recorded there | confirmed by the lens's replays; not re-run by the lead |

## 03, 04, 05, 06 (checked 30 Sep ~08:50; code unchanged since the lenses ran — only `docs/` moved)

| id | checked at | verdict |
| --- | --- | --- |
| UX-18 | `PickRow.tsx:238` `lost && 'opacity-60'` | confirmed, never batched |
| UX-21 | `PlayerProfilePage.tsx:160` `pick.status === 'lost' && 'opacity-60'` | confirmed |
| UX-25 | `CurrentRoundPage.tsx:459-467` — `isError` renders `EmptyState` "No coupon this week yet" with the raw error message | confirmed |
| UX-26 | `TabBar.tsx:173` indicator `absolute top-0` with no `left-0` | confirmed |
| UX-31 = DES-16 | no `networkMode` anywhere in `apps/web/src`; TanStack Query's default `online` pauses the pick mutation offline, so `usePickEditor.ts`'s Batch 90 offline branch never runs | confirmed — **one defect, two ids; the register keeps UX-31** |
| DES-10 | `AppToaster.tsx:40-46` `<Toaster richColors …>` with no `theme` prop (sonner defaults to light), and `index.css:430-434` (from `4121cf0`) forces the title to `var(--text-primary)` — near-white in dark mode, on sonner's pale light-theme fills | confirmed by mechanism; lens 06 measured 1.01-1.07:1 |
| DES-11 | production stylesheet `index-Br02Ny1y.css` fetched 28 Sep: `bg-primary\/15`, `border-error\/40`, `bg-error\/10` — 0 occurrences each; plain `bg-primary` present; `tailwind.config.ts` colours are `var(--…)` with no `<alpha-value>` | confirmed **against production** |
| DES-17 | `DashboardPage.tsx:334-337` — first-run copy whenever `leagueCount === 0`, which is also the loading and error value | confirmed |
| DES-20 | lead saw "taken by Former" / "Picked by Dan, Former" in the (unstyled) settled-coupon capture on 29 Sep | confirmed — the lead's own observation, recorded as DES-20 rather than a second id |
| PERF-18 | `football_data.py:945-952` — `resolve_names` awaited once per competition in a loop | confirmed |
| PERF-19 | the arithmetic of `coupon.py:30-40` run verbatim: 30 × 7.40, 40 × 4.50 and 50 × 3.40 raise `decimal.InvalidOperation`; 50 × 3.30 passes | confirmed by the lead |
| PERF-23 | `routers/picks.py:118, 138` both `"50/hour;100/day"` | confirmed |
| OPS-17 | `scheduler.py` — `misfire_grace_time` set once (`:1088`, the switched-off backup) | confirmed |
| FEAT-A13 | `admin.py:1348` correct one pick by id; no web caller | confirmed (lens drive: 0 of 17 reads return another member's pick id) |
| FEAT-A12 | `auth.py:426` checks the switch before the name | confirmed (lens) |

**Corpus.** Lens 06 found 26 of lens 03's "happy"/"firstrun" captures were taken with the
browser still offline (banner visible, some content missing). None of lens 03's findings rests
on them — UX-25's error captures carry no banner — but axe runs on those six screens in that
state may have under-reported. They are marked in `screenshots/INDEX.md`; lens 06 re-captured
the screens.
