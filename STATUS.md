# Status — The Coupon

## Now

**Batch 1 of 6 shipped to local `main` (commit `8513a02`). Next: Batch 2 — Betfair adapter.**

👉 Full context: `HANDOFF.md` (repo root) + `docs/BUILD_PLAN.md`.

**Done (Batch 1):** ported app-starter's clean PIN/invite auth + profile + notification
spine into this repo (replacing calcio's email-first tangle); reconciled calcio's
leagues/memberships/join-requests onto it (`CurrentPlayer`→`CurrentUser`,
`per_player_key`→`per_user_key`, site-admin via `UserRole.admin`, `avatar_url` stubbed);
reduced `scheduler.py` to the app-starter framework (backup + connection-warmup);
rebuilt `main.py`/`models/__init__.py`; squashed calcio's 40 WC migrations to a single
`001_baseline` (profiles · refresh_tokens · push/notif tables · audit_log · leagues ·
memberships · join_requests · invites). Added a minimal `services/notification_triggers.py`
(the `notify_member_joined` the routers need). Dropped `bootstrap_admin.py` for
app-starter's `seeds.py`.

**Verified green:** import-compiles (37 routes) · `ruff check` + `ruff format` clean ·
`mypy --strict` (34 files, 0 issues) · 76 spine tests pass · baseline migration
applies/reverses/re-applies on a real (pgserver) Postgres with all 9 tables + 6 enums
+ constraints + updated_at trigger correct · **league routers driven end-to-end on real
Postgres** (login → create → list mine → 2nd user join-by-code → detail shows both
members). See scratchpad `verify_migration.py` / `e2e_leagues.py`.

**Toolchain (no coupon venv exists):** run lint/type/test with app-starter's venv —
`/Users/craigrobinson/app-starter/apps/api/.venv/bin/{ruff,mypy,python}` — and
`PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api`. DB checks use the pip `pgserver`
package (local Homebrew postgres is broken). The loaded calcio `CLAUDE.md` points at
calcio's venv — ignore it for this repo.

**Next step:** Batch 2 — Betfair adapter (`services/betfair.py` + `FakeBetfair`):
login/keepAlive, slate, odds, settlement; unit-tested against canned responses.
Then Batches 3–6 (Pick/scoring → scheduler jobs → frontend → verify + rebrand).

**Known Batch-1 gaps (deferred by design):** league *routers* have no committed tests yet
(spine tests cover auth/notifications/backup/scheduler; leagues proven via the e2e script) —
port/reconcile calcio's `test_leagues`/`test_join`/`test_invites` when convenient. Docs
rebrand (`AGENTS.md`/`README.md`/`.env.example` still calcio/WC) + `HANDOFF.md` deletion
are Batch 6.

**Key decisions (settled — don't re-litigate):** base = calcio clone · auth = pure
PIN/invite (port app-starter's) · odds = Betfair Exchange (only free source with the
Scottish lower leagues — verified) · scope = English pyramid + full Scottish · mechanic
= one unique odds-scored pick per member per gameweek.

**Gotchas:** web needs Node 20; backend deps `--prefer-binary`; scratch Postgres via
pip `pgserver`; `/Users/craigrobinson/app-starter` is the infra reference; Betfair live
check is Craig's to run (agent never logs into his money account); API keys stay in
`.env`, never the repo.

## Log

- 2026-07-24 — Cloned calcio → the-coupon; stripped WC backend; locked auth = PIN/invite;
  wrote HANDOFF.md + BUILD_PLAN.md. Handed off mid-Batch-1.
- 2026-07-25 — **Batch 1 shipped** (`8513a02`, on local `main`). Ported app-starter spine,
  reconciled leagues, squashed to `001_baseline`, reduced scheduler. Green: compile · ruff ·
  mypy --strict · 76 tests · migration + league e2e on real Postgres. Also reconciled the
  close-out workflow to this repo (BUILD_PLAN-driven, local-first) and cleared calcio's stale
  batch docs. Next = Batch 2 (Betfair adapter).
