# Status — The Coupon

Current state only, and every claim carries the date it was last checked. History is in
`session-log.md`: one entry per batch, newest last, plus this page's old narrative archived
at the top of that file. Open work is at the head of `docs/BUILD_PLAN.md`.

**Keeping it this size.** When a fact changes, rewrite its line and its date; do not add a
paragraph beneath it. A batch's story belongs in its `session-log.md` entry, not here.

## Live

Checked 2026-09-27 unless a line says otherwise.

| | |
| --- | --- |
| API | `api-production-109b1.up.railway.app` serves `c671ccf9` at migration `026` |
| API deployment | Railway `07af30bc-5395-4f88-a75a-3f0957921928`, one replica, `europe-west4` |
| Web | `the-coupon-production.vercel.app`, `c671ccf9`; Vercel builds `main` on every push |
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

- **`/ship-prod` is owed for Batch 115 and its production-measurement fix.** The API-only
  changes add no schema: the request-budget suite now derives the largest round from
  PostgreSQL, browsed odds loosen from 2h / 1h / 30m to 4h / 2h / 1h, and the daily walk
  is remeasured at 23 played competitions. The certified worst day is 481 of 500 requests.
  Production remains Railway `07af30bc` (`c671ccf9`) at migration `026`.
- **Rollback is a plain redeploy.** That shipment applied no migration, so its baseline —
  Railway `d295c44a-ea26-4575-9bb7-469f2e6d8cf1`, the previous image — boots against the
  database as it stands, and rolling the API back alone hides Batch 148's dialog. Vercel's
  last build without the dialog is `dpl_8mU9qpVZ6pqZQXErPHHH8Rp9uqpe`.

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

- **Member B has not been told their sign-in name changed** (2026-09-27, 10:45 BST). Batch
  74 renamed the owner and members A and B on 2026-08-26; the boot-time push reached the
  other two on 2026-08-30. Member B has no push subscription, but five live sessions, the
  latest issued 2026-09-26 06:11 UTC. Batch 148's in-app notice has been live since 09:42
  BST, so it reaches them on their next open; the API logs `rename notice seen in the app`
  when it does, and production then holds the third `display_name_changed` row.
- A rename releases the old sign-in name outright, so nothing reserves the three names
  Batch 74 released.

## Open batches

Five rows are open (2026-09-27); they are at the head of `docs/BUILD_PLAN.md`:

1. **`/group-start Z` — 151 → 140 → 168 → 150 → 149**, the rest of the visual pass.
   Web-only with no stops: each reaches members on its own close-out push. The order and
   its reasons are under Group Z in `docs/review/2026-09-13/08-sequencing.md`.

## Toolchain

Checked 2026-09-24.

- **The gate is `scripts/ci-local.sh`**: eleven checks and no skips. It refuses a test
  count that falls, or that rises without `scripts/ci-test-counts.env` being raised
  (backend 1,342, frontend 1,187). 11 to 13 minutes on this Mac, and 38 when macOS's storage scan loads it (2026-09-25). Without a database the
  backend suite was 780 passed and 520 skipped at 1,300 tests — not the gate. Current
  ratchets are 1,350 backend and 1,197 frontend tests.
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
- **Production reads**: the direct IPv6 database connection works — `railway run` with the
  explicit production selectors, then a local asyncpg script (2026-09-27); `railway ssh`
  worked on 2026-09-26. Both routes have flipped before, so probe rather than trust this
  line. The Railway CLI's default link is staging, and the Supabase MCP here is a
  different product — never read Coupon data through it.
- **Vercel CLI**: run it with Node 20 first on `PATH` (the ambient `node` is 14 and cannot
  load it). Its stored token is short-lived and refreshed by any `vercel` command, so run
  `vercel whoami` before reading it for a REST call (2026-09-26).
- **Deploys**: the web app ships on every push to `main`; the API ships only through
  `/ship-prod`.
