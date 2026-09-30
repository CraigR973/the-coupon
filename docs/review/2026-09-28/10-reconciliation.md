# 10 — Reconciliation against the code

Every finding in this review re-checked by the lead against the source at the final commit,
after the lenses finished. The review changed nothing outside `docs/`, so the code is
`main`'s (`eb18bcb`) throughout. The working notes behind this table are
`notes/lead/reconciliation.md`.

**Outcome: every finding confirmed at its stated location. One raised (SEC-32, from an owner
decision to a HIGH finding), one merged (DES-16 into UX-31), no withdrawals.** Two capture
defects were found and contained — the lead's own harness built an unstyled bundle, and 26 of
lens 03's captures were taken offline — and neither changes a finding. They are written up first,
because a register that never corrects itself is not being checked.

## Raised

**SEC-32 — a league admin can take over any member of their league, and every other league that
member plays in.** Lens 01 recorded the ordinary-member case of SEC-15 as an owner decision. The
lead registers it as a HIGH finding, for three reasons found in the source:

- The only recorded decision near it (the Batch 66 row, 2026-08-23) chose the reset *mechanism* —
  clear the PIN, let the member set their own — when only the *site* console could reset. The
  league-scoped route came later and hands that mechanism to any league admin, and anyone can
  create a league.
- The guard's own comment (`league_memberships.py:625-628`) states the invariant: a league admin
  must never open the claim window "on an account whose privileges reach beyond an ordinary
  membership in this league". The check (`:629-640`) considers only admin roles, not membership
  of other leagues.
- `credentials.clear_pin` (`:72-95`) notifies nobody; `/auth/pin/set` (`auth.py:791-850`) is
  unauthenticated for 24 hours.

Same-league takeover was reproduced end to end by lens 01 (Carol; Hank via SEC-27). The reach
into a second league follows from the session being the victim's account — tokens carry no
league scope. Rated HIGH by the rubric ("credentials exposed under an unusual but reachable
condition"), as 2026-09-13 rated SEC-15 for the same case. Disproof attempted: the 10/hour rate
limit does not stop a targeted takeover; the audit row is visible only to the resetting league's
admins; the victim is signed out, not warned.

## Merged

**DES-16 is UX-31.** Both describe the silent spinner when a pick is tapped with the connection
gone. One cause (no `networkMode` anywhere in `apps/web/src`, so TanStack Query pauses the
mutation), one fix, one batch (172). The register keeps UX-31.

## Contained — capture defects, no finding changed

- **The lead's harness built an unstyled bundle.** `notes/harness/web.sh` ran Vite from outside
  `apps/web`, so Tailwind's cwd-relative `content` globs matched nothing and the stylesheet was
  9.1 KB instead of 45.8 KB. Found by lens 03 on 29 Sep, fixed at 18:50 (the script now builds
  from `apps/web` and refuses a stylesheet under 30 KB). Lens 02's three and lens 05's six
  captures were built with it; they are relabelled `-unstyled-` and used only as text evidence
  (CORR-21's prices, CORR-26's "4 of 3", FEAT-B07's journey), which the unstyled page shows
  correctly. Lens 01's CSP check was functional, not visual. Lenses 03, 04 and 06 built
  correctly.
- **26 of lens 03's captures were taken offline.** Lens 06 found the offline banner in 26 "happy"
  and "firstrun" captures of six screens (create league, discover, join by code, league members,
  league settings, My Leagues), some with content missing. No lens-03 finding rests on them —
  UX-25's error captures carry no banner — but axe runs on those six screens in that state may
  have under-reported. Marked in `screenshots/INDEX.md`; lens 06 re-captured them (`*-l06--*`).

## The register, line by line

| id | verified at | verdict |
| --- | --- | --- |
| SEC-27 | `league_memberships.py:627-640` reads current admin memberships only; demotion unguarded against a following reset | confirmed |
| SEC-28 | `routers/auth.py:329-344` — lock written and committed, then `charge_failure()`; `rate_limit.py:330-351` — charger invoked only after the PIN check | confirmed |
| SEC-29 | `league_memberships.py:364-390` — `_effective_name_taken` scoped to the league's current members; no re-check on join | confirmed |
| SEC-30 | lens OSV output; Batch 127 row "OPS-15 is left out" | confirmed |
| SEC-31 | `league_memberships.py:438` — `display_name_hint` with no `max_length` | confirmed |
| SEC-32 | see "Raised" | confirmed, raised |
| CORR-19 | the completion hook is called from `league_memberships.py:345`, `leagues.py:1773`, `admin.py:443` — not from `me.py:625 delete_my_account` | confirmed |
| CORR-20 | `_same_week_round_may_settle` referenced only at `scoring.py:76, 201` | confirmed |
| CORR-21 | `scoring.py:773`, `me.py:469`, `me.py:552` pass every leg to `combined_odds`; only `coupon.py` filters void | confirmed |
| CORR-22 | `admin.py correct_pick` sends nothing | confirmed |
| CORR-23 | `scoring.py` returns `{}` when no pick is pending | confirmed |
| CORR-24 | `scheduler.py:508-522` passes the raw pool; `gameweek.py:1065` charges `len(set(competition_ids))`; `scheduler.py:578-586` refresh passes no budget | confirmed |
| CORR-25 | `backfill_season_calendar.py:61-65` joins `League` without a `deleted_at` filter | confirmed |
| CORR-26 | `CouponSection.tsx:130` — `${legCount} of ${memberCount}` against today's roster | confirmed |
| CORR-27 | erasure and leave keep picks (Batch 136 design); lens reproduction | confirmed |
| CORR-13 | label derivation unchanged by Batch 121; lens reproduction | confirmed, carried |
| UX-18 | `PickRow.tsx:238` `lost && 'opacity-60'` | confirmed, carried and never batched |
| UX-21 | `PlayerProfilePage.tsx:160` same | confirmed |
| UX-25 | `CurrentRoundPage.tsx:459-467` renders `EmptyState` on `isError` | confirmed |
| UX-26 | `TabBar.tsx:173` indicator with no `left-0` | confirmed |
| UX-31 | no `networkMode` in `apps/web/src` | confirmed (DES-16 merged) |
| UX-22, 23, 24, 27-30, 32, 33 | lens captures, axe re-runs and keystroke logs in `notes/03-ux/` | confirmed by the lens's re-runs; not re-driven by the lead |
| PERF-18 | `football_data.py:945-952` awaits `resolve_names` per competition | confirmed |
| PERF-19 | `coupon.py:30-40`'s arithmetic run verbatim: 30 × 7.40, 40 × 4.50, 50 × 3.40 raise `InvalidOperation` | confirmed by the lead |
| PERF-20 | lens reproduction over HTTP (`push_fanout.py`); `database.py:19-21` pool 5 + 5, timeout 10 s | confirmed |
| PERF-21 | as CORR-24 (refresh half) | confirmed |
| PERF-22 | `apps/web/package.json` lists `framer-motion`; no chunk contains it | confirmed |
| PERF-23 | `routers/picks.py:118, 138` both `"50/hour;100/day"` | confirmed |
| OPS-17 | `scheduler.py` sets `misfire_grace_time` once (`:1088`, the switched-off backup) | confirmed, carried |
| OPS-19 | `ship-prod.md` Node 20 paths (lens) | confirmed |
| FEAT-A12 | `auth.py:426` checks the switch before the name | confirmed, carried |
| FEAT-A13 | `admin.py:1348`; no web caller (`route_inventory.txt`) | confirmed |
| FEAT-A14 | `leagues.py:1358` scope matches `target_id`/`league_slug` only; writers at `admin.py:1286, :1432` record neither | confirmed |
| FEAT-A15, B09-B12 | lens route inventory and drives | confirmed |
| DES-10 | `AppToaster.tsx:40-46` no `theme`; `index.css:430-434` forces `--text-primary` | confirmed by mechanism |
| DES-11 | production's `index-Br02Ny1y.css`: `bg-primary\/15`, `border-error\/40`, `bg-error\/10` absent; `tailwind.config.ts` colours `var(--…)` without `<alpha-value>` | confirmed against production |
| DES-12-15, 17-23 | lens captures (99, all distinct by hash) and source | confirmed; DES-17 at `DashboardPage.tsx:334-337`, DES-20 seen by the lead too |
| PIPE-10 | `ci-local.sh:36` runs the guardrail from the working tree | confirmed |
| PIPE-12 | `gh run list --limit 300`: 72 runs on `main` since 20 Sep, 8 failed. `--branch main` silently returns only 16 of them — it first read as 6 | confirmed |
| PIPE-11, 13-19 | lens replays and commit ids in `notes/07-pipeline/` | confirmed by the lens's replays |

## What this means for the batches

Batches 169-203 were drafted after this pass, so none needs revising. SEC-32 travels in 179 with
SEC-27. DES-16 has no batch of its own; 172 carries UX-31.
