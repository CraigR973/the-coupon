# Status — The Coupon

Current state only, and every claim carries the date it was last checked. History is in
`session-log.md`: one entry per batch, newest last, plus this page's old narrative archived
at the top of that file. Open work is at the head of `docs/BUILD_PLAN.md`.

**Keeping it this size.** When a fact changes, rewrite its line and its date; do not add a
paragraph beneath it. A batch's story belongs in its `session-log.md` entry, not here.

## Live

Checked 2026-09-24 unless a line says otherwise.

| | |
| --- | --- |
| API | `api-production-109b1.up.railway.app` serves `13431987` at migration `026` |
| API deployment | Railway `8701d8c3-7102-4fa5-a108-515bd762937e`, one replica, `europe-west4` |
| Web | `the-coupon-production.vercel.app`; Vercel builds `main` on every push |
| Database | Supabase `pugujiiojitstkilphrz`, London; RLS forced on 21 of 21 tables (2026-09-23) |
| League data | 1 live league, 13 active accounts, 7 active push subscriptions |
| Odds | `odds-api.io` priced by Bet365; 100 requests/hour and 500/day for the whole deployment |
| Football data | FotMob, no key |
| Scheduler | on (`SCHEDULER_ENABLED=true`) |
| Avatars | built and off (`AVATAR_STORAGE=none`) |
| Backups | **none** — no managed backup and no PITR (Batch 95) |

`scripts/check-deploy-drift.sh` is the authority on what the API is running, never
`git log`: shipments have gone unrecorded before.

## Owed

- **`/ship-prod` for Batches 155 and 153.** 155's boot-time rename notice now finds its
  three profiles by id; 153 changed only a docstring. Before them production was in sync
  (drift check, 2026-09-24), so nothing else is waiting.
- **The direct-database recheck skipped at the Phase 7 shipment.** RLS, the
  `anon`/`authenticated`/`PUBLIC` grants and Batch 146's two indexes were last confirmed
  in full on 2026-09-23. Run it before the next shipment — inside the container over
  `railway ssh`, since the database host does not resolve from this Mac (2026-09-24).
- **Rollback needs the runbook.** Phase 7 applied `026`, so the previous deployment
  (`673b9f15-4c81-492d-a498-290fc306de90`) is a target only through
  `docs/runbooks/migration-026-recovery.md`, not a plain redeploy.

## Waiting on the owner

These are not batches; nothing here will happen unless the owner does it or authorises it.

- **Renew the Vercel CLI token** (`vercel login`). Its API answered 403 on 2026-09-24, so
  the commit a web deployment carries cannot be confirmed from here.
- **The season-calendar backfill.** Production's `season_calendars` table is empty
  (2026-09-24). `python -m src.backfill_season_calendar --dry-run`, review every move,
  then a separately authorised `--apply`; see `docs/backfills/2026-season-calendar.md`.
- **Batch 95's two prerequisites:** a backup destination off the platform (S3, R2,
  Backblaze) with credentials, and headroom on the Supabase egress quota whose consumer
  was never identified (FEAT-A09; the quota was exceeded on 2026-08-25, last checked
  2026-08-28).
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

Thirteen rows are open (2026-09-24); they are at the head of `docs/BUILD_PLAN.md`. The run
order agreed on 2026-09-24:

1. **127** — CI, the local gate and the web build still run Node 20, out of support since
   2026-04-30.
2. **142** — web push has no timeout and its endpoint check ignores the port; the
   `cryptography` pin is held at 48.0.1 by owner decision.
3. **95** — no second copy of the scored history. Blocked on the owner items above.
4. **134** — a mis-settled pick can only be corrected by a script against production.
5. **136** — no self-service deletion or data export. UK GDPR questions go to the owner.
6. **135** — nothing tells a member their round has settled.
7. **148** — the rename notice has no channel but push.
8. **115** — nothing learns until a member arrives. Once recorded here as superseded by
   Batch 119; re-verify before building.
9. **150** — the first screen a new member sees.
10. **149** — toasts, skeletons, and errors that look like empty states.
11. **151** — one statistic drawn two ways; no type scale.
12. **168** — two links under minimum target size; 200% zoom.
13. **140** — the desktop layout is the phone layout stretched.

Known before starting:

- **127 edits protected gate files.** The guardrail now carries the owner's named
  exception for it (2026-09-24): `ci.yml`, `ci-local.sh` and `apps/web/package.json` only.
- **136 and 148 change API and web**, so close-out refuses them until the owner
  explicitly schedules the matching `/ship-prod`.

## Toolchain

Checked 2026-09-24.

- **The gate is `scripts/ci-local.sh`**: eleven checks and no skips. It refuses a test
  count that falls, or that rises without `scripts/ci-test-counts.env` being raised
  (backend 1,300, frontend 1,180). 11 to 13 minutes on this Mac. Without a database the
  backend suite is 780 passed and 520 skipped — not the gate.
- **Backend** runs from the gate's own venv, `~/.cache/the-coupon/ci-local-venv`, built from
  `apps/api/requirements-dev.txt`: Python 3.12, FastAPI 0.141.1, ruff 0.5.4. app-starter's
  venv cannot import the suite.
- **Frontend** is Node 20.20.2 through nvm and pnpm 9.15.0. The ambient `node` is too old
  for the tooling.
- **Scratch PostgreSQL** is pip `pgserver`, started and discarded by the gate.
- **Protected files**: `scripts/assert-quality-guardrails.sh` fails any batch that edits
  the gate scripts, the CI workflow, the close-out workflow, `apps/web/package.json`,
  `apps/api/requirements-dev.txt`, or the lint, type and build configuration — unless the
  owner has named that batch and those files in the script, while its row is open.
- **Production reads**: `railway ssh` with the explicit production selectors works; the
  direct IPv6 database connection does not (2026-09-24). The Railway CLI's default link is
  staging, and the Supabase MCP here is a different product — never read Coupon data
  through it.
- **Deploys**: the web app ships on every push to `main`; the API ships only through
  `/ship-prod`.
