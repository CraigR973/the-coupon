# Status — The Coupon

Current state only, and every claim carries the date it was last checked. History is in
`session-log.md`: one entry per batch, newest last, plus this page's old narrative archived
at the top of that file. Open work is at the head of `docs/BUILD_PLAN.md`.

**Keeping it this size.** When a fact changes, rewrite its line and its date; do not add a
paragraph beneath it. A batch's story belongs in its `session-log.md` entry, not here.

## Live

Checked 2026-10-10 unless a line says otherwise.

| | |
| --- | --- |
| API | `api-production-109b1.up.railway.app` serves `b7a4d72` (through Batch 216) at migration `031` (25 Oct) |
| API deployment | Railway `205b3765-b52e-443f-8923-15e0e371834c` succeeded, a variable-only redeploy of the same `b7a4d72` image for the bookmaker switch (31 Oct); one replica, `europe-west4` (25 Oct) |
| Payments | `payments-production-0aa1.up.railway.app` serves `b7a4d72` at `031`, Railway `d2ba459a-ecfe-483e-bb25-7ba55c0a6bc1`, one replica, `europe-west4`, no access log; **Monzo connected** at 21:32 UTC (owner's account, confidential client, webhook registered); payments count from 21:29 UTC (16 Oct); 2-1 Hibs has its link id and all 20 link payments from members were read and matched, through the five-minute read, because every webhook re-read is refused; the owner's own top-ups into the pot are matched since Batch 216 (the pot's `pot_…` name learned from Monzo's filings), and the first one waits in the queue once; Monzo's approval lapses about 14 Jan 2027 (25 Oct) |
| Web | Batch 202's build (Vite 8, Tailwind 4) is live at `the-coupon-production.vercel.app` from `628aa0a` (2026-10-11: its stylesheet served, sign-in rendered at 390 and 1280 px with no console errors). Later documentation-only deployments leave the web code unchanged. |
| Database | Supabase `pugujiiojitstkilphrz`, London; RLS forced on 27 of 27 tables, no public-role grants (25 Oct) |
| League data | 1 live league, 13 active accounts, 7 active push subscriptions (2026-09-24) |
| Odds | `odds-api.io` priced by **Betfair Sportsbook** since 10:36 UTC on 31 Oct (ADR 0002's 31 Oct amendment). Bet365 has been paid-only since 26 Oct, 19:00 UTC, and a free key gets a 403. Free key: 100 requests/hour and 500/day for the whole deployment. On the 31 Oct card it priced 78 of 85 fixtures, none in the Highland League (31 Oct). The owner chose to keep it rather than pay £49/mo for Bet365 (31 Oct) |
| Football data | FotMob, no key |
| Scheduler | on (`SCHEDULER_ENABLED=true`) |
| Avatars | built and off (`AVATAR_STORAGE=none`) |
| Backups | **none yet** — the weekly off-site job is live and switched off (Batch 95) |

`scripts/check-deploy-drift.sh` is the authority on what the API is running, never
`git log`: shipments have gone unrecorded before.

## Shipment state

- **Batch 205 is shipped and verified** (13 Oct, `9731776`). API health and database
  readiness report `028`, drift is in sync, and the read-only audit found RLS forced on all
  24 tables with no `anon`, `authenticated` or `PUBLIC` table or schema grants. The web alias
  is Ready on the same SHA. Pay to pick is inert until a site admin sets a league's fee.
- **Batch 206 is live on the web** (13 Oct, `32a8aef`, web-only, exact-SHA CI green): the pay
  panel, the season pot, the site-admin fee fields and the Payments screen. No league has a
  fee, so no member sees any of it yet.
- **Batch 209 is shipped and verified** (14 Oct, `335e986`, no migration). Every member of a
  league with a fee gets the payment link with no 18+ step, and pick cards grey out while a
  member owes. Health reports `335e986` / `028`, drift is in sync, and the read-only audit found
  RLS forced on 24 of 24 tables with no `anon`, `authenticated` or `PUBLIC` grants. Vercel serves
  the same SHA. Still inert until a site admin sets a league's fee.
- **Batches 207 and 208 are shipped and verified** (16 Oct, `5dd1fbe`, migration `029`). Both
  services report `5dd1fbe` / `029`, drift is in sync for both, and the read-only audit found
  RLS forced on 25 of 25 tables with no `anon`, `authenticated` or `PUBLIC` grants.
  **Monzo is connected** (16 Oct): the owner created a new confidential client, sealed its id and
  secret, connected at 21:29 UTC and approved in the app; the service marked itself connected and
  registered its webhook at 21:32 UTC with no error. Payments count from 21:29 UTC. Nothing is
  read until a league has a `monzo_link_id`, which a site admin now sets in League settings
  (Batch 210). The connect's one-time OAuth code appeared in the payments access log once; it was
  spent, and since `bca0aaa` (shipped 17 Oct) the service writes no access log.
- **Batch 203 shipped unrecorded on 11 Oct** (Railway `de1b8aa8`, `5882b0f`), found from
  Railway's deployment list on 13 Oct and now in the L4 record.
- **Batch 216 is shipped and verified** (25 Oct, `b7a4d72`, no migration). Both services report
  `b7a4d72` / `031` and drift is in sync. The first read learned the pot's `pot_…` name from a
  link payment's filing and wrote nothing; the owner's two earlier moves fell before it.
- **The bookmaker switch is live** (31 Oct, API `205b3765`, no code change, no migration).
  Every pick in the 31 Oct round was refused until `ODDS_API_BOOKMAKER` moved from `Bet365`
  to `Betfair Sportsbook`. Health reports `b7a4d72` / `031` and drift is in sync. A refused
  fixture's live odds call now returns Betfair Sportsbook prices, and a member's pick then
  saved (`201`). The restart emptied the app's odds budget counter, so a `429` at 11:05
  refused picks again until about 11:10, and they have saved since. The payments service was
  not touched. Record: L4, 2026-10-31.
- **The 24 Oct round is settled by hand** (31 Oct, 17:33 UTC, no code change). The owner
  approved voiding the abandoned Cumbernauld Colts v Banks O'Dee tie, so its one pick scores
  nothing; the round's other 10 picks had already settled, and all 12 members were told. It
  ran the admin settle endpoint's own code from the owner's Mac, because Railway SSH was
  dropping connections; the audit row names the owner. Record: L4, 2026-10-31.
- **Batch 214 is shipped and verified** (25 Oct, `06d6070`, migration `031`). Both services
  report `06d6070` / `031`, drift is in sync, and the catalogue audit found RLS forced on 27 of 27
  tables with no public-role grants. The payments service learned 2-1 Hibs' pot from its link
  payments, but Monzo names that pot by a different id in pot deposits, so the owner's top-ups
  are still not matched (Batch 216). Migration `031` requires forward recovery:
  `docs/runbooks/migration-031-recovery.md`.
- **Batch 213 is shipped and verified** (18 Oct, `0a7457b`, migration `030`). Both services
  report `0a7457b` / `030`, drift is in sync, and the catalogue audit found RLS forced on 26 of 26
  tables with no public-role grants. The `payment_notices` job runs every ten minutes; its first
  run sent nothing. Migration `030` requires forward recovery:
  `docs/runbooks/migration-030-recovery.md`.
- **Migration `029` requires forward recovery.** It is additive, but the older images'
  boot checks cannot start against revision `029`. Use
  `docs/runbooks/migration-029-recovery.md` for forward repair. Production has no backup
  restore point, so do not describe a downgrade as a data-preserving rollback.

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
- **Stop recording the owner's own £1 by hand** (2026-10-25). Since Batch 216 a move from the
  owner's account into the pot is read; the first one waits in "Waiting to be matched" once,
  and assigning it to the owner books every later one automatically.
- **Monzo needs approving again by about 14 Jan 2027.** Monzo makes the owner re-approve a
  developer app every 90 days, and the payments service was approved on 16 Oct; after
  that nothing is read until the owner connects again from the payments service. Batch 214
  adds a warning a week before (2026-10-24).
- **Delete the old Monzo spike's OAuth client** at developers.monzo.com (ADR 0009 launch
  step 1, still open). Its client secret, echoed into a transcript on 7 Sep, still works: a
  token refresh with it succeeded on 2026-10-24. Its data access lapsed the same day, and
  the payments service has its own client, so nothing needs it.

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
complete (Batches 171, 175–178; web-only, closed 8 Oct); Group AF is complete, shipped
and verified (Batches 196, 195, 197 and 194; final shipment 10 Oct). Group AH: Batches 202
(web toolchain refresh) and 203 (pipeline and operations hygiene) are complete (11 Oct).
Batch 203 shipped on 11 Oct, unrecorded until 13 Oct.

Batches 205-209 are pay to pick in 2-1 Hibs (ADR 0009). Batch 205 — the API ledger, weekly
dues and the paid-up check, migration `028` — is complete and shipped (13 Oct, `9731776`).
Nothing changes for members until a site admin sets a league's fee. Batch 206 — the screens —
is complete and live on the web (13 Oct, `32a8aef`). Batch 209 — the link with no 18+ step,
and greyed pick cards while a member owes (ADR 0009 amended 13 Oct) — is complete (14 Oct,
`b53ddf9`) and shipped as `335e986`. Batch 207 — the `payments` Railway service declared and
switched off, with a boot that never migrates — is complete (14 Oct, `71a0c5a`); production's
service was switched on on 16 Oct (`8b26336`). Batch 208 — the payments service reads the
league's Monzo link payments into the ledger, migration `029` — is complete (16 Oct,
`22bc3cb`) and not shipped; one `/ship-prod` covers both. Batch 210 — the admin-screen half of
208 (the link-id field and link health) — is complete and live on the web (17 Oct, `1e12109`,
web-only). Batch 211 —
a least-privilege database login for `payments` — is open and deferred until after launch
(owner, 16 Oct). Batch 212 — members see the prize fund, both targets and everyone's status,
and the pay panel's earlier balance — is complete and shipped (17 Oct, `06a32f6`, shipped as
`88d8541`). Batch 213 — notifications for queued payments, Monzo link trouble and payments
received, migration `030` — is complete and shipped (18 Oct, `8797aa7`, shipped as `0a7457b`).
2-1 Hibs has its fee, link and link id, and members' link payments are read and matched (24
Oct); making sure every member is 18 or over stays the owner's check (ADR 0009). Batch 214 —
the owner's own top-ups into the pot, a warning before Monzo's 90-day approval lapses, and
the refused webhook re-reads logged, migration `031` — is complete and shipped (25 Oct,
`d4880b1`, shipped as `06d6070`). Batch 216 — the owner's top-ups matched by the pot's
`pot_…` name, learned from Monzo's filings, which are never counted — is complete (25 Oct,
`bbedccf`) and shipped (25 Oct, as `b7a4d72`). Batch 215 — why Monzo refuses every webhook
re-read — is open.

## Toolchain

Checked 2026-10-03.

- **The gate is `scripts/ci-local.sh`**: twelve checks and no skips, the twelfth being the seeded
  coupon journey (2026-09-30). GitHub's `coupon-journey` job runs the same runner through
  `ci-local.sh --journey-only`. The `gate` job runs the same trusted-main guard, ratchets and
  zero-skip checks as local close-out. A full green run stamps the exact Git tree; close-out reuses
  that stamp when only `docs/BUILD_PLAN.md`, `session-log.md` and `STATUS.md` changed, otherwise it
  reruns the gate, and waits for both pushed SHAs to pass CI before the group continues. It refuses a test
  count that falls, or that rises without `scripts/ci-test-counts.env` being raised
  (backend 1,548, frontend 1,408, journey 1; checked 2026-10-17). 13m04s on this Mac
  with the journey (2026-09-30), and 38 minutes when macOS's storage scan loads it
  (2026-09-25). Without a database the backend suite is 800 passed and 550 skipped at
  1,350 tests (2026-09-29) — not the gate.
- **Backend** runs from the gate's own venv, `~/.cache/the-coupon/ci-local-venv`, built from
  `apps/api/requirements-dev.txt`: Python 3.12, FastAPI 0.141.1, ruff 0.5.4. app-starter's
  venv cannot import the suite.
- **Frontend** is Node 24.21.0 through nvm, with pnpm 9.15.0 from corepack; the gate refuses
  any other pnpm. CI and the Vercel build are Node 24 too (`apps/web` pins `24.x`). The
  ambient `node` is too old for the tooling, and nvm's default alias is still 20. Since Batch
  202 (2026-10-11): Vite 8 (Rolldown), Vitest 5, Tailwind 4 reading `tailwind.config.ts`
  through `@config`, ESLint 10 with `apps/web/eslint.config.js`; OSV finds no npm advisory.
  `index.css` holds the rules that keep Tailwind 3's rendering — change them only with a
  before/after screenshot check. The guard does not yet protect `eslint.config.js`.
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
- **Operator CLIs**: Railway 5.64.2 and Vercel 54.6.1 are verified with Node 24.21.0 on
  `PATH`; the legacy Node 20 installation supplies their shims only. Its stored token is short-lived and refreshed by any `vercel` command, so run
  `vercel whoami` before reading it for a REST call (2026-09-26).
- **Deploys**: the web app ships on every push to `main`; the API ships only through
  `/ship-prod`. Close-out refuses API+web work, and web work over existing API debt, until the
  owner schedules the shipment; its durable verdict records who scheduled it and the UTC time.

**Next:** the owner's next move into the pot (Sat 31 Oct) confirms the booking; then Batch
215. The season-calendar backfill remains owner-gated,
unblocked since 4 Oct.
