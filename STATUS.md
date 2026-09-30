# Status — The Coupon

Current state only, and every claim carries the date it was last checked. History is in
`session-log.md`: one entry per batch, newest last, plus this page's old narrative archived
at the top of that file. Open work is at the head of `docs/BUILD_PLAN.md`.

**Keeping it this size.** When a fact changes, rewrite its line and its date; do not add a
paragraph beneath it. A batch's story belongs in its `session-log.md` entry, not here.

## Live

Checked 2026-09-28 unless a line says otherwise.

| | |
| --- | --- |
| API | `api-production-109b1.up.railway.app` serves `b08a47f3` at migration `026` |
| API deployment | Railway `86f9ba84-b72d-4791-80ab-c3730ccd9032`, one replica, `europe-west4` |
| Web | `the-coupon-production.vercel.app` serves `main` at `4121cf0`, Batch 149's last web change — its stylesheet was checked live on 2026-09-28; Vercel builds `main` on every push |
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

- **No `/ship-prod` is owed.** Batch 115 and its 23-competition measurement fix shipped on
  2026-09-27 as Railway `86f9ba84` (`b08a47f3`); the drift check reports **in sync**, and
  the budget suite certifies 481 of 500 provider requests for browsing, discovery, the weekly
  walk, one warm pass and the manual allowance. That is not a ceiling: it omits the
  twice-daily refresh, settlement and the pick bucket. A measured one-window Saturday is 289
  (review 2026-09-28, lens 04).
- **Rollback is a plain redeploy.** The shipment applied no migration, so its baseline —
  Railway `e77dde8f-9bf3-4c6c-9080-addf52504307`, the previous `c671ccf9` image — boots
  against the database as it stands. Vercel was already on `b08a47f3` at
  `dpl_3robg45FXRnNWsmETNvrs1dagtL6`, so the web app did not move during `/ship-prod`.

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

Batches 170-203 are drafted from the 2026-09-28 review and every owner decision they needed
was answered on 30 Sep. Batches 169, 198 and 200 completed on 30 Sep; Group AG resumes at Batch
199, then 201 before its `/ship-prod` checkpoint. Groups AA, AC, AD, AE, AB, AF and AH follow
in that order (`docs/agent-commands/group-start.md`; the reasons are in the review's
`08-sequencing.md`).

## Toolchain

Checked 2026-09-24.

- **The gate is `scripts/ci-local.sh`**: twelve checks and no skips, the twelfth being the seeded
  coupon journey (2026-09-30). GitHub's `coupon-journey` job runs the same runner through
  `ci-local.sh --journey-only`; its first GitHub run is Batch 200's close-out push. A full green run stamps the
  exact Git tree; close-out reruns it after the documentation commit and refuses a push without
  that matching stamp. It refuses a test
  count that falls, or that rises without `scripts/ci-test-counts.env` being raised
  (backend 1,350, frontend 1,212, journey 1). 13m04s on this Mac with the journey (2026-09-30), and
  38 minutes when macOS's storage scan loads it (2026-09-25). Without a database the backend suite is
  800 passed and 550 skipped at 1,350 tests (2026-09-29) — not the gate.
- **Backend** runs from the gate's own venv, `~/.cache/the-coupon/ci-local-venv`, built from
  `apps/api/requirements-dev.txt`: Python 3.12, FastAPI 0.141.1, ruff 0.5.4. app-starter's
  venv cannot import the suite.
- **Frontend** is Node 24.21.0 through nvm, with pnpm 9.15.0 from corepack; the gate refuses
  any other pnpm. CI and the Vercel build are Node 24 too (`apps/web` pins `24.x`). The
  ambient `node` is too old for the tooling, and nvm's default alias is still 20.
- **Scratch PostgreSQL** is pip `pgserver`, started and discarded by the gate.
- **Protected files**: `scripts/ci-local.sh` runs `main`'s guard and owner-approval table, not the
  branch's. The guard protects gate, close-out, CI, lint, type and test-discovery configuration by
  pattern; it also refuses recorded skip, suppression and weakened-oracle forms. An approved
  gate-maintenance batch must have its exact file list quoted in its open row on `main`.
- **Production reads**: the direct IPv6 database connection works — `railway run` with the
  explicit production selectors, then a local asyncpg script (2026-09-27); `railway ssh`
  worked on 2026-09-26. Both routes have flipped before, so probe rather than trust this
  line. The Railway CLI's default link is staging, and the Supabase MCP here is a
  different product — never read Coupon data through it.
- **Vercel CLI**: run it with Node 20 first on `PATH` (the ambient `node` is 14 and cannot
  load it). Node 20 is end-of-life; it stays here only until the CLIs are re-tested on
  Node 24 (review 2026-09-28, OPS-19). Its stored token is short-lived and refreshed by any `vercel` command, so run
  `vercel whoami` before reading it for a REST call (2026-09-26).
- **Deploys**: the web app ships on every push to `main`; the API ships only through
  `/ship-prod`.
