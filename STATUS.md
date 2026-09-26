# Status — The Coupon

Current state only, and every claim carries the date it was last checked. History is in
`session-log.md`: one entry per batch, newest last, plus this page's old narrative archived
at the top of that file. Open work is at the head of `docs/BUILD_PLAN.md`.

**Keeping it this size.** When a fact changes, rewrite its line and its date; do not add a
paragraph beneath it. A batch's story belongs in its `session-log.md` entry, not here.

## Live

Checked 2026-09-26 unless a line says otherwise.

| | |
| --- | --- |
| API | `api-production-109b1.up.railway.app` serves `fccbfa90` at migration `026` |
| API deployment | Railway `dbe274e8-b15a-4c06-a4a2-3de5997cad92`, one replica, `europe-west4` |
| Web | `the-coupon-production.vercel.app`, `fccbfa90`; Vercel builds `main` on every push |
| Database | Supabase `pugujiiojitstkilphrz`, London; RLS forced on 21 of 21 tables, no public-role grants |
| League data | 1 live league, 13 active accounts, 7 active push subscriptions (2026-09-24) |
| Odds | `odds-api.io` priced by Bet365; 100 requests/hour and 500/day for the whole deployment |
| Football data | FotMob, no key |
| Scheduler | on (`SCHEDULER_ENABLED=true`) |
| Avatars | built and off (`AVATAR_STORAGE=none`) |
| Backups | **none yet** — the weekly off-site job is live and switched off (Batch 95) |

`scripts/check-deploy-drift.sh` is the authority on what the API is running, never
`git log`: shipments have gone unrecorded before.

## Owed

- **No `/ship-prod` is owed.** Batch 135 shipped on 2026-09-26 at 17:28 BST as Railway
  `dbe274e8` (`fccbfa90`), ahead of that evening's settle sweep; the drift check reports
  **in sync**, and a read-only recheck found 21 of 21 tables with RLS forced and no grants
  to `anon`, `authenticated` or `PUBLIC`.
- **Rollback is a plain redeploy.** That shipment applied no migration, so its baseline —
  Railway `cf8b924e-8952-41b6-97c6-dbfce02412c3`, the previous image — boots against the
  database as it stands. Vercel's baseline is `dpl_JQv72Dzik7xHBUyzSsyqtATt377g`.

## Waiting on the owner

These are not batches; nothing here will happen unless the owner does it or authorises it.

- **The season-calendar backfill.** Production's `season_calendars` table is empty
  (2026-09-24). `python -m src.backfill_season_calendar --dry-run`, review every move,
  then a separately authorised `--apply`; see `docs/backfills/2026-season-calendar.md`.
- **Switch on the weekly backup** — Batch 95 is live and off (2026-09-26). Create
  the EU-jurisdiction R2 bucket with a 30-day bucket lock and a 90-day expiry, a key
  scoped to it, check Supabase egress headroom (FEAT-A09's consumer was never identified;
  the quota was exceeded on 2026-08-25), seal the `BACKUP_*` variables and run it once by
  hand. Steps: `docs/runbooks/backup-restore.md`. Until then production has no backup.
- **The local agent configuration** (review finding PIPE-01, by hand, not a batch).
  `.claude/settings.local.json` still enables the Supabase MCP server — bound to a
  different product — with its write-capable query tool allowed, a blanket shell allow,
  and delete rules for other repositories (checked 2026-09-24).
- **Avatars stay off** until the owner follows `docs/runbooks/avatar-storage.md`. They
  would share the Supabase project whose egress quota was exceeded.

## Members

- **Member B has not been told their sign-in name changed** (2026-09-24). Batch 74 renamed
  the owner and members A and B on 2026-08-26; the boot-time notice reached the other two.
  Member B has no push subscription, so every boot retries and nothing arrives — Batch
  148's case.
- A rename releases the old sign-in name outright, so nothing reserves the three names
  Batch 74 released.

## Open batches

Seven rows are open (2026-09-26); they are at the head of `docs/BUILD_PLAN.md`. The run
order agreed on 2026-09-24:

1. **148** — the rename notice has no channel but push.
2. **115** — nothing learns until a member arrives. Once recorded here as superseded by
   Batch 119; re-verify before building.
3. **150** — the first screen a new member sees.
4. **149** — toasts, skeletons, and errors that look like empty states.
5. **151** — one statistic drawn two ways; no type scale.
6. **168** — two links under minimum target size; 200% zoom.
7. **140** — the desktop layout is the phone layout stretched.

Known before starting:

- **148 changes API and web**, so close-out refuses it until the owner explicitly
  schedules the matching `/ship-prod`.

## Toolchain

Checked 2026-09-24.

- **The gate is `scripts/ci-local.sh`**: eleven checks and no skips. It refuses a test
  count that falls, or that rises without `scripts/ci-test-counts.env` being raised
  (backend 1,342, frontend 1,187). 11 to 13 minutes on this Mac, and 38 when macOS's storage scan loads it (2026-09-25). Without a database the
  backend suite was 780 passed and 520 skipped at 1,300 tests — not the gate.
- **Backend** runs from the gate's own venv, `~/.cache/the-coupon/ci-local-venv`, built from
  `apps/api/requirements-dev.txt`: Python 3.12, FastAPI 0.141.1, ruff 0.5.4. app-starter's
  venv cannot import the suite.
- **Frontend** is Node 24.21.0 through nvm, with pnpm 9.15.0 from corepack; the gate refuses
  any other pnpm. CI and the Vercel build are Node 24 too (`apps/web` pins `24.x`). The
  ambient `node` is too old for the tooling, and nvm's default alias is still 20.
- **Scratch PostgreSQL** is pip `pgserver`, started and discarded by the gate.
- **Protected files**: `scripts/assert-quality-guardrails.sh` fails any batch that edits
  the gate scripts, the CI workflow, the close-out workflow, `apps/web/package.json`,
  `apps/api/requirements-dev.txt`, or the lint, type and build configuration — unless the
  owner has named that batch and those files in the script, while its row is open.
- **Production reads**: `railway ssh` with the explicit production selectors works; the
  direct IPv6 database connection does not (2026-09-26). The Railway CLI's default link is
  staging, and the Supabase MCP here is a different product — never read Coupon data
  through it.
- **Vercel CLI**: run it with Node 20 first on `PATH` (the ambient `node` is 14 and cannot
  load it). Its stored token is short-lived and refreshed by any `vercel` command, so run
  `vercel whoami` before reading it for a REST call (2026-09-26).
- **Deploys**: the web app ships on every push to `main`; the API ships only through
  `/ship-prod`.
