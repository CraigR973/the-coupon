# 09 — Reconciliation against the code

Every finding in this review re-checked against the source on `2ce6f42`, after
the fact, because the review ran over seven days across five usage-limit
interruptions and its working notes were lost to a temporary-directory cleanup.
The purpose is to make sure the register describes the code as it actually is
before any of it is built.

**Outcome: 44 of 46 findings confirmed at the stated location, one refined, one
withdrawn.** The withdrawal and the refinement are written up first, because a
register that never corrects itself is not being checked.

## Withdrawn

**SEC-24 — "admin extra-week endpoints skip the Saturday-only rule the anchor
move enforces".** Wrong, and wrong in a way worth recording. The anchor move does
enforce a Saturday (`season_calendar.py:209` refuses an anchor whose weekday is
not Saturday), but an *extra week* is by definition a non-canonical date — a
midweek round. `declare_extra_week` refuses a date that is already canonical,
which is the opposite check and the correct one. Requiring a Saturday there would
forbid the only thing the feature exists to express. The finding misread a
deliberate asymmetry as a missing guard. **No batch.**

Note this does not touch CORR-11, which is a different and real gap in the same
function: it has no *past-date or settled* guard.

## Refined

**PERF-04 — the index claim was half right.** `picks` is indexed: a composite
`ix_picks_league_gameweek` on `(league_id, gameweek_id)` plus
`ix_picks_player_id`. The composite is left-anchored on `league_id`, so it cannot
serve the lookups that filter on `gameweek_id` alone — the existence check inside
stranded-round retirement and the settle sweep — which is what the stress-shape
plans showed scanning. And `gameweeks.starts_on`, which the retirement and
discovery queries range over, has no index at all.

Restated: **the gap is a `gameweek_id`-only pick lookup that the left-anchored
composite cannot serve, and an unindexed `gameweeks.starts_on`** — not "picks are
unindexed". Batch 146 carries the corrected version.

## Checked and held

**DES-01** claimed zero large-breakpoint utilities. A first grep found two `lg:`
hits, which looked like a contradiction; both turned out to be size-variant keys
in the avatar and button components (`lg: 'h-14 w-14'`), not responsive prefixes.
There are genuinely **zero responsive `lg:` or `xl:` utilities** in the
application. The claim stands.

**DES-02** (the pick screen opens with every competition collapsed) is verified
from the screenshot corpus rather than from a pinned line of code; the collapse
state lives in the competition-group component and was not isolated. Treated as
verified-by-observation, and the batch says where to look.

## The register, line by line

| id | verified at | verdict |
| --- | --- | --- |
| SEC-15 | `league_memberships.py:476-530` (no role check on target) + `auth.py:757-815` (unauthenticated `pin/set`) | confirmed |
| SEC-16 | `remove_member` contains no rotation; `join_league_by_code` checks only active membership and capacity | confirmed |
| SEC-17 | `deps.py:32-56` — docstring says site admins bypass; `if player.role == UserRole.admin: return league`, on reads and writes alike | confirmed |
| SEC-18 | `auth.py:27-28` — 5 attempts, 15-minute lock, account-wide | confirmed |
| SEC-19 | `apps/web/vercel.json` sets only Cache-Control, Permissions-Policy, Referrer-Policy, X-Content-Type-Options | confirmed |
| SEC-20 | `league_memberships.py:305-327` — override stored with only a length bound | confirmed |
| SEC-21 | `cryptography==48.0.1` pinned; three advisories, none reachable | confirmed |
| SEC-22 | 17 advisories, all dev/build transitive | confirmed |
| SEC-23 | `push_notification_service.py:68` — `webpush(` called with no timeout | confirmed |
| SEC-24 | — | **withdrawn** |
| SEC-25 | `tokens.ts:3-6` clears access/refresh/player only; `leagueRecency.ts:3` key survives | confirmed |
| SEC-26 | `league_memberships.py:79` — `select(League).where(League.id == invite.league_id)`, no `deleted_at` | confirmed |
| CORR-08 | `picks.py:311-317` — rollback then `_taken_detail(league)` on an expired object | confirmed |
| CORR-09 | `gameweek.py:871` bound `starts_on <= max(cadence)`, `:874` no-picks exclusion, `:1337` settle with no per-week guard, `scoring.py` sums all season rounds | confirmed |
| CORR-10 | `me.py:361` — `win_rate_pct = 100 * picks_won / picks_played`, and `scoring.py:309-321` keeps `picks_played` and `picks_priced` distinct | confirmed |
| CORR-11 | `season_calendar.py:248-263` — guards are season, calendar-exists, already-canonical; **no past or settled check** | confirmed |
| CORR-12 | `season_calendar.py:105-133` — returns early if a calendar exists, anchors from the passed date, never recomputed | confirmed |
| CORR-13 | follows CORR-09; the `b` suffix derives only for declared extras | confirmed |
| CORR-14 | no completion call anywhere in `league_memberships.py` or the admin deactivation path | confirmed |
| CORR-15 | `scheduler.py` docstring states the cost as `windows x dates x competitions` and records the 2×2×67 incident | confirmed |
| CORR-16 | `football_provider.py:232-237` — `season_for` splits on calendar month | confirmed |
| CORR-17 | `scheduler.py:903-914` — `CronTrigger(minute=15, timezone="Europe/London")` | confirmed |
| CORR-18 | `me.py:194-201` — `avg_rank` and `avg_rank_leagues` on the cross-league summary | confirmed |
| UX-12 | `ForgotPinPage`, `SetPinPage`, `JoinPage` have no `<main>` and no `<h1>`; `BrowserOnboarding` has an `<h1>` but no `<main>`; `LoginPage` has both | confirmed |
| UX-13 | `TeamSeasonPage.tsx:209` and `SeasonStrip.tsx:80` — `opacity-70` over tuned tokens | confirmed |
| PERF-01 | `labels_for_gameweeks` called twice in `me.py` (`:442`, `:527`), plus `gameweek.py` and `leagues.py` | confirmed |
| PERF-02 | `nixpacks.toml:26` — `uvicorn src.main:app` with no `--workers` | confirmed |
| PERF-03 | no compression middleware anywhere in `main.py` | confirmed |
| PERF-04 | see "Refined" | refined |
| PERF-05 | `database.py:8-11` — `pool_size=10, max_overflow=10` | confirmed |
| OPS-11 | `.nvmrc` = 20, engines `>=20.0.0`, CI pins `node-version: "20"` in three jobs | confirmed |
| OPS-12 | `phase-closeout.md` and `ship-prod.md` — reasoning holds | confirmed |
| OPS-13 | `run_scheduled_backup` is defined and callable on demand but has **no `add_job`**; `config.py:302` defaults the destination to a container path | confirmed |
| OPS-14 | `discovery_health.py` contains no push, notify or send | confirmed |
| OPS-16 | `me.py:10` docstring claims nine queries | confirmed |
| FEAT-A10 | `admin.py:1187-1219` — refuses an already-settled round; docstring says correction "is not this endpoint"; no correction route exists | confirmed |
| FEAT-A11 | `rename_notice.py` — web push only; the marker is written only on delivery | confirmed |
| FEAT-A12 | `public_signup` appears nowhere in `apps/web/src` | confirmed |
| FEAT-B07 | only `admin.py:366 delete_player`; no self-service deletion, no export route | confirmed |
| FEAT-B08 | triggers are member-joined, provider-trouble, picks-open, pick-made — **no settlement trigger** | confirmed |
| FEAT-B09 | `ResultsPage.tsx` references `season_week` as a label only; no filter or selector | confirmed |
| DES-01 | zero responsive `lg:`/`xl:` (see above) | confirmed |
| DES-02 | screenshot corpus | verified by observation |
| DES-03 | 57 `toast.error` against 44 `toast.success`, no warning variant | confirmed |
| DES-04 | `App.tsx:146` — `<Toaster position="bottom-right" />`, no offset | confirmed |
| DES-05 | `.animate-shimmer` defined at `index.css:398`, **zero users** | confirmed |
| DES-09 | `tailwind.config.ts` defines no `fontSize` or `lineHeight` | confirmed |
| PIPE-02 | hook text identical in both configurations | confirmed |
| PIPE-03 | `ci-local.sh:154` — `vite preview` with **no `--port` and no `--strictPort`**, then `sleep 5` | confirmed (and worse than reported: the port is not even specified) |
| PIPE-04 | `ci-local.sh` `step()` writes output to a log and prints it only on failure | confirmed |
| PIPE-05 | `phase-closeout.md` pushes at step 8 (line 51) and runs the drift check at line 67 — **after** | confirmed |
| PIPE-06 | `AGENTS.md:123`, `phase-closeout.md:20`, `batch-verify.md:21` and `:26` | confirmed |
| PIPE-08 | names present in `STATUS.md`, `docs/BUILD_PLAN.md`, `docs/backfills/2026-08-names-and-numbers.md` | confirmed |

## What this means for the batches

Batches 120-140 were drafted from the register before this reconciliation and
none of them is invalidated by it. Batch 146 carries PERF-04 in its corrected
form. SEC-24 has no batch. Batches 141-155 cover the remainder of the register,
so that every finding now has either a batch, an owner decision, or an explicit
"accepted, no action".
