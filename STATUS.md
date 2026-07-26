# Status — The Coupon

## Now

**Batch 3 of 6 shipped to local `main` (commit `433f0ae`). Next: Batch 4 — Scheduler.**

👉 Full context: `HANDOFF.md` (repo root) + `docs/BUILD_PLAN.md`.

**Done (Batch 3):** the weekly mechanic — `gameweeks`/`fixtures`/`picks` tables (migration
`002`), `services/{gameweek,scoring,coupon}.py`, and `routers/{picks,gameweek,coupon}.py`.
The submit endpoint snapshots live Betfair odds server-side and enforces both rules — one
pick per member per gameweek (a re-pick updates in place), no two members on the same
selection — with the two `picks` unique constraints as the race backstop. Scoring is
`round(odds×10)` on the winning runner; the combined coupon is the product of the legs.
Gameweek + fixture are global (one slate per Saturday); only the pick is league-scoped.

**Done (Batch 2):** built `services/betfair.py` — the odds source. Abstract `BetfairAdapter`
holds the domain logic (`fetch_slate` Saturday-15:00 filter · `fetch_odds` MATCH_ODDS + BTTS
priced-only snapshot with HOME/DRAW/AWAY · YES/NO mapping · `settle` on runner `WINNER`);
`Betfair` (live httpx: interactive login/keepAlive, JSON-RPC, retry/backoff) and `FakeBetfair`
(canned catalogues/books, `with_sample_data` + `close_markets`) override only the raw
primitives, so tests drive the real domain code. Added `BF_APP_KEY`/`BF_USER`/`BF_PASS` to
config. No tables added → no migration.

**Verified green:** `ruff check` + `ruff format` clean · `mypy --strict` (35 files, 0 issues) ·
98 pytest (76 spine + 22 new). The 22 exercise FakeBetfair slate/odds/settlement and the live
client's HTTP layer (login/keepAlive/RPC parse+error+5xx-retry) via `httpx.MockTransport` — no
live Betfair session touched.

**Done (Batch 1):** app-starter PIN/invite auth + profile + notification spine ported over
calcio's email-first tangle; leagues/memberships/join-requests reconciled onto it; `scheduler.py`
reduced; calcio's 40 WC migrations squashed to `001_baseline`. (Detail in `session-log.md` /
`git show 8513a02`.)

**Toolchain (no coupon venv exists):** run lint/type/test with app-starter's venv —
`/Users/craigrobinson/app-starter/apps/api/.venv/bin/{ruff,mypy,python}` — and
`PYTHONPATH=/Users/craigrobinson/the-coupon/apps/api`. DB checks use the pip `pgserver`
package (local Homebrew postgres is broken). The loaded calcio `CLAUDE.md` points at
calcio's venv — ignore it for this repo.

**Next step:** Batch 4 — Scheduler: APScheduler jobs to refresh slate+odds a few times
pre-lock, lock the gameweek at 14:30, settle Saturday evening + recompute standings, and
push pick reminders. Wire `services/gameweek.sync_slate` + `scoring.settle_gameweek` into
scheduled jobs; introduce a cached/shared Betfair session so it stops logging in per request
(Batch 3's `get_betfair_adapter` logs in on every pick). Then Batches 5–6 (frontend reshape
→ verify + rebrand).

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
- 2026-07-25 — **Batch 2 shipped** (`21078d6`, on local `main`). Betfair adapter
  (`services/betfair.py`): `BetfairAdapter` ABC + live `Betfair` + `FakeBetfair`; slate /
  odds snapshot / settlement, priced-only rule, Saturday-15:00 (Europe/London) filter. Green:
  ruff · ruff format · mypy --strict · 98 tests (no migration — no tables). Next = Batch 3
  (Pick + scoring engine).
- 2026-07-26 — **Batch 3 shipped** (`433f0ae`, on local `main`). Pick + scoring engine:
  gameweek/fixture/pick tables (migration `002`), `services/{gameweek,scoring,coupon}.py`,
  `routers/{picks,gameweek,coupon}.py`; submit snapshots live odds + enforces uniqueness both
  ways, scoring `round(odds×10)`, combined acca. Green: ruff · ruff format · mypy (44 files) ·
  116 pytest + 3 skipped; pgserver: alembic 001→002 clean + pick/settle/standings/acca flow.
  Next = Batch 4 (scheduler).
