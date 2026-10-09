# Status — The Coupon

Current state only, and every claim carries the date it was last checked. History is in
`session-log.md`: one entry per batch, newest last, plus this page's old narrative archived
at the top of that file. Open work is at the head of `docs/BUILD_PLAN.md`.

**Keeping it this size.** When a fact changes, rewrite its line and its date; do not add a
paragraph beneath it. A batch's story belongs in its `session-log.md` entry, not here.

## Live

Checked 2026-10-07 unless a line says otherwise.

| | |
| --- | --- |
| API | `api-production-109b1.up.railway.app` serves `c530469` at migration `026` |
| API deployment | Railway `3219c196-8b5e-40b8-8558-d313d901faf6`, one replica, `europe-west4` |
| Web | Batch 195 `eb9fcee` was pushed to `main` on 9 Oct; its production deployment has not been independently verified. The last verified deployment was Batch 178 `f13934c` (`6944760442`, checked 8 Oct) |
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

- **`/ship-prod` is owed after Batch 197.** The Group AF shipment was scheduled by Craig
  Robinson at 2026-10-09 10:29:55 UTC; Batch 195's safety acknowledgement was recorded at
  22:29:48 UTC. The API still serves Group AE's `c530469` at migration `026`. The new
  sign-up route and invite registration wait for the explicit shipment; the web uses the
  existing registration flow while that route is absent.
- **Rollback is a plain redeploy.** The shipment applied no migration, so its baseline —
  Railway `98fed46d-c15f-445d-98ac-b36aa004b57b`, the previous image redeployed by the
  pinned IaC apply — boots against the database as it stands. Vercel was already on
  `c530469` at `dpl_9inCkfDwnT7hFwHfKPVFhR72okGC`, so the web app did not move for the release.

## Waiting on the owner

These are not batches; nothing here will happen unless the owner does it or authorises it.

- **The season-calendar backfill**, unblocked since Batch 188 shipped on 2026-10-04.
  Production's `season_calendars` table is empty
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
was answered on 30 Sep. Group AG is complete, shipped and verified. Group AA is complete
(172, 173, 174 and 170, closed 3 Oct; web-only, nothing to ship). Group AC is complete,
shipped and verified (180, 179, 181 and 182; shipped 3 Oct as `9be47cef`). Group AD's first
checkpoint shipped on 4 Oct as `bb09760b` (Batches 183 and 188), and its closing checkpoint
shipped on 5 Oct as `546db3f` (Batches 184-187 and fix `f0710b0`); Group AD is complete. Batch
204 (docs-only close-out fast path, owner-approved gate maintenance) is complete. Group AE is
complete, shipped and verified (Batches 189–193; shipped 7 Oct as `c530469`); Group AB is
complete (Batches 171, 175–178; web-only, closed 8 Oct); Group AF has closed Batches 196
and 195 and continues with 197; Group AH follows
(`docs/agent-commands/group-start.md`).

## Toolchain

Checked 2026-10-03.

- **The gate is `scripts/ci-local.sh`**: twelve checks and no skips, the twelfth being the seeded
  coupon journey (2026-09-30). GitHub's `coupon-journey` job runs the same runner through
  `ci-local.sh --journey-only`. The `gate` job runs the same trusted-main guard, ratchets and
  zero-skip checks as local close-out. A full green run stamps the exact Git tree; close-out reuses
  that stamp when only `docs/BUILD_PLAN.md`, `session-log.md` and `STATUS.md` changed, otherwise it
  reruns the gate, and waits for both pushed SHAs to pass CI before the group continues. It refuses a test
  count that falls, or that rises without `scripts/ci-test-counts.env` being raised
  (backend 1,420, frontend 1,304, journey 1; checked 2026-10-09). 13m04s on this Mac
  with the journey (2026-09-30), and 38 minutes when macOS's storage scan loads it
  (2026-09-25). Without a database the backend suite is 800 passed and 550 skipped at
  1,350 tests (2026-09-29) — not the gate.
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
- **Production reads**: use `railway run` with the explicit production selectors and a local
  asyncpg script. The direct Supabase hostname did not resolve locally on 2026-10-01, so the
  read-only audit used the exact project's London session-pooler route in memory; `railway ssh`
  worked on 2026-09-26. Probe rather than trusting either route. The Railway CLI's default
  link is staging, and the Supabase MCP here is a different product — never read Coupon data
  through it.
- **Vercel CLI**: run it with Node 20 first on `PATH` (the ambient `node` is 14 and cannot
  load it). Node 20 is end-of-life; it stays here only until the CLIs are re-tested on
  Node 24 (review 2026-09-28, OPS-19). Its stored token is short-lived and refreshed by any `vercel` command, so run
  `vercel whoami` before reading it for a REST call (2026-09-26).
- **Deploys**: the web app ships on every push to `main`; the API ships only through
  `/ship-prod`. Close-out refuses API+web work, and web work over existing API debt, until the
  owner schedules the shipment; its durable verdict records who scheduled it and the UTC time.

**Next:** Group AF Batch 195 (closed sign-up and invite registration); and the owner's
season-calendar backfill, now unblocked.
