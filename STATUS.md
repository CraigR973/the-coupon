# Status — The Coupon

## Now

**Mid-build, Batch 1 of 6. Backend does NOT compile yet. Nothing committed.**

👉 **Read `HANDOFF.md` first** (repo root) for full context, then `docs/BUILD_PLAN.md`.

**Done:** cloned from calcio (no secrets, fresh git init on `main`); stripped all
World-Cup backend modules. **Spine kept:** auth · leagues/memberships/join-requests ·
notifications · backup · push (but their imports are still broken from the strip).

**Next step:** finish Batch 1 — port app-starter's clean PIN/invite auth+notification+
profile spine into this repo, reconcile calcio's leagues to it, reduce `scheduler`,
squash to a baseline migration, get compiling + ruff/mypy green. Then Batches 2–6
(Betfair adapter → Pick/scoring → scheduler jobs → frontend → verify).

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
