# Common brief — every lens of the 2026-09-28 review

You are one specialist pass of the fourth standing review of The Coupon. The lead
owns verification, reconciliation and the README; you own one lens document and
its notes. Read this whole file, then your lens brief, then start.

## The repo and the review

- Repo `/Users/craigrobinson/the-coupon`, branch `chore/review-2026-09-28` (already
  checked out in the main working tree — **never switch branches there**, never
  `git stash`, `git reset`, `git checkout <branch>` or `git rebase` in it; other
  passes are working in the same tree at the same time).
- The full prompt is `docs/review/2026-09-28/00-prompt.md`. Read it. The previous
  review is `docs/review/2026-09-13/` — read its README and your own lens's
  document there before starting.
- `AGENTS.md` is the project's instructions; follow it.
- Batches 120-168 plus 95 and 115 closed since the last review (commit `2ce6f42`).
  Their rows are in `docs/BUILD_PLAN.md` (Batch 95 at ~line 3173, Batches 120-167
  from ~line 4234, and 115/140/148/149/150/151/168 at the head of the file under
  "Open batches", ticked). `session-log.md` has one entry per batch, newest last.

## Deployment state (verified by the lead, 28 Sep 2026 22:40-22:48 BST)

- `scripts/check-deploy-drift.sh`: production API serves `b08a47f3` at migration
  `026`; `main` is `eb18bcb`, 14 commits ahead, **none of which reach the API
  image** → in sync, exit 0.
- Production web (`https://the-coupon-production.vercel.app`) serves CSS that
  contains the last web commit's change (`4121cf0`, Batch 149's toast offset), so
  the web is at `main` too.
- Therefore **every finding on current `main` is `live`** unless you find a
  specific reason it is not. Say so if you do.

## Hard guardrails (breaking any of these ends the review)

- **Never `cd`** in a shell command. On this machine `cd` is an autoenv function
  that executes `.env` files and has printed secrets into transcripts. Use
  absolute paths, `git -C`, `ls <path>`. When a script needs a working
  directory, run it as `bash script.sh` so its internal `cd` is the builtin, or
  pass `cwd=` from Python.
- **Production is read-only**: HTTPS response headers, `GET /api/v1/health`,
  and public unauthenticated pages only. No writes, no load, no signing in as
  any real member, no production database reads, no Railway, Vercel or Supabase
  commands of any kind. **Never use any `mcp__supabase__*` tool** — it is bound
  to a different product.
- **Never call odds-api.io, Betfair or FotMob live.** The scheduler shares the
  100/hour odds budget and a probe can 429 the refresh job. All automation uses
  `ODDS_PROVIDER=fake` (the harness sets it).
- `apps/web/.env.local` points at **another product's** API. Never run the web
  app without overriding `VITE_API_URL` (the harness does this).
- **Never pass `DATABASE_URL` to `psql`** (its failure path prints the DSN). The
  harness's scratch clusters have no password, but keep the habit.
- **Fix nothing.** Do not edit any file outside `docs/review/2026-09-28/`. If you
  find a doc-only correction (a stale number, a wrong claim in a doc), list it in
  your notes under "Doc corrections" with file, from, to — the lead applies them.
- Do not install anything into the repository (no `pnpm add`, no edits to
  `package.json` or requirements — those are protected files). If you need a
  tool that is not present, install it under the scratchpad (below) with
  `npm install --prefix <scratchpad>/tools/<name>` from the public npm registry,
  and record the exact version.
- Do not run `scripts/ci-local.sh` in the main working tree (the lead runs the
  gate; a second run collides on `apps/web/dist` and port 4173).
- Never bind ports **4173, 5173 or 8000** (the gate and the e2e flow own them).
  Use only the ports in your lens brief.
- WebKit cannot be installed on this Mac. Use Playwright's **Chromium**.

## The shared harness (smoke-tested by the lead)

`docs/review/2026-09-28/notes/harness/` — read both files before use.

- `stack.py` — one process that holds a scratch PostgreSQL (pgserver) open, runs
  `alembic upgrade head`, and serves `tests.e2e_server:app` (FakeBetfair odds,
  scheduler off) on your port, optionally calling `POST /__e2e/seed` (Alice,
  Bob, Carol, PIN `1234`, league `the-coupon`, one open round). It writes
  `<scratchpad>/stack-<name>.json` with the scratch `database_url`, so you can
  also drive the database and services in process from the same venv. Run it in
  the background with the gate's venv:
  `~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/harness/stack.py --name <lens> --api-port <port> --origin http://127.0.0.1:<web-port> --seed`
  Kill it with SIGTERM when done. `--no-api` gives you just the database.
  The e2e server also exposes `POST /__e2e/lock` and `POST /__e2e/settle`.
- `web.sh <name> <api-origin> <web-port>` — builds the **production** bundle
  with `VITE_API_URL` set to your local API into `<scratchpad>/web-<name>` and
  serves it with `vite preview --strictPort`. It refuses to serve a bundle that
  does not reference your API origin.
- Verified by the lead: API health, HTTP login as Alice, the bundle build, and a
  real Chromium sign-in through the bundle at 1280×800 (the four PIN digits are
  four separate inputs; type one digit into each). Playwright is importable from
  `/Users/craigrobinson/the-coupon/apps/web/node_modules/@playwright/test/index.mjs`
  and runs with Node 24: `. ~/.nvm/nvm.sh && nvm use 24 --silent && node x.mjs`.
  axe-core 4.10.2 is at `apps/web/node_modules/axe-core/axe.min.js`.
- Not verified by the lead, from memory notes: under 768px width the app may
  show its install onboarding instead of `/login` (sign in at desktop width and
  then resize, or set storage state); the Batch 166 session-log entry records
  that the app's durable login limit (5 per 15 minutes) trips when a script signs
  in on every run — sign in once and reuse storage state.
- Seed anything more complex (more leagues, members, windows, markets,
  `pick_scope`, settled seasons) in process against the scratch database with
  the app's own models and services, from a script you keep in your notes dir.
- The machine is a 4-core, 8 GB Intel Mac shared by up to six passes. Keep
  exactly one stack per lens, stop it when idle, and stop everything at the end.
- Scratchpad (pgdata, bundles, logs, throwaway files — never notes):
  `/private/tmp/claude-501/-Users-craigrobinson-the-coupon/3c37fb9f-68c1-4af0-88c9-13ef38e101fd/scratchpad`

## Notes, progress and commits (the last review lost its notes)

- All working notes go in your lens's notes dir under
  `docs/review/2026-09-28/notes/` — scripts, command output, probe transcripts,
  measurements. Never in /tmp or the scratchpad.
- Keep `<your notes dir>/progress.md` current: what is done, what is in flight,
  the exact next step. If you are interrupted, a fresh session must be able to
  continue from it alone.
- Commit your own paths only, at every natural checkpoint and at the end:
  `git -C /Users/craigrobinson/the-coupon add <your paths>` then
  `git -C /Users/craigrobinson/the-coupon commit -m "docs(review): <lens> — <what>" -- <your paths>`
  with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  If git reports `index.lock`, wait five seconds and retry — another pass is
  committing. Never commit anything outside your paths, never push.
- Screenshots go in `docs/review/2026-09-28/screenshots/` named
  `<route>--<state>--<width>--<theme>.png`, and each capture is listed in
  `screenshots/INDEX.md` by the pass that took it (append, do not rewrite others'
  rows).

## Evidence standard

- Every finding: **id, severity, live/main-only, verified or plausible, evidence**
  (file:line, command and output, HTTP exchange, axe result, or screenshot
  path), **a one-sentence impact on a member**, and **a recommended fix**.
- "Verified" means reproduced against something running. Code reading alone is
  "plausible".
- Before rating anything HIGH or above, try to disprove it and record what you
  tried.
- Severity. CRITICAL: picks, points or credentials are wrong, lost or exposed
  now. HIGH: the same under an unusual but reachable condition, or the Saturday
  flow can fail. MED: degraded correctness, security or efficiency with a
  workaround. LOW: hardening, hygiene, polish. INFO. Design findings use impact
  (high/med/low) instead.
- Don't pad. If you find nothing material, say so and show what you checked.
- Do not reopen recorded owner decisions (text-only with no crests; display name
  + four-digit PIN; SEC-14 accepted; FotMob terms accepted; logical backups, not
  PITR; account deletion anonymises and keeps history; cryptography held at
  48.0.1; void legs excluded from the combined coupon; no rank across leagues;
  name redaction in the working tree only, no history rewrite) unless you find
  new facts — and then say exactly what changed.

## Your lens document

`docs/review/2026-09-28/0N-<name>.md`, in the house style of the 2026-09-13
documents (read yours there). It opens with:

1. **Method** — what you ran, against what.
2. **Prior findings** — a table covering your slice of the 2026-09-13 register:
   `id | batch | held / regressed / partial / not fixed | evidence`. "Held" means
   re-driven against something running, not re-read. Say how you drove it.
3. **Register** — new findings, ids continuing the prior numbering (given in
   your lens brief), then one section per finding with the fields above.
4. **Checked and found nothing material**, **Proposed batches** (one line each,
   with web-only / API-carrying / migration), **Owner decisions** (options + a
   recommendation), **Doc corrections**, **What this pass did not do**.

## When you finish

Stop every process you started, commit, and reply to the lead with at most 40
lines: the prior-findings tally (held / regressed / partial / not fixed), each
new finding as `id · severity · live/main-only · verified/plausible · one line`,
anything you could not do, and the doc corrections you listed. The detail
belongs in your document, not in the reply.
