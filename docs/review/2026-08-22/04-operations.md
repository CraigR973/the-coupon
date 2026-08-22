# 04 — Operations, tooling and the gate

Where the process, rather than the code, is load-bearing.

## OPS-01 · MED · The local gate skips 151 tests, and close-out does not wait for CI

Three individually reasonable decisions compose into a gap:

1. `tests/conftest.py:38-41` skips every Postgres-backed test when
   `DATABASE_URL` is unset, "so the default unit-test job stays hermetic".
2. `docs/agent-commands/batch-verify.md` treats the database run as conditional
   — "when database behavior is in scope".
3. `docs/agent-commands/phase-closeout.md` merges, ticks and **pushes `main`**,
   and closes with "Do not poll CI — those remain separate, explicit actions."

So the routine gate is `pytest` with no `DATABASE_URL`, which is **509 passed,
151 skipped**. The skipped set is not peripheral: it is the HTTP pick flow,
settlement, the scheduler jobs, slate persistence, team matching, seeds, and all
four migration tests. A batch can go green locally, merge, and push to `main`
— which auto-deploys the web app to production through Vercel — without the core
game logic having been executed at all, and without CI having reported.

CI does set `DATABASE_URL` (`.github/workflows/ci.yml:33`) and does run them, so
the tests are not decorative. The gap is that nothing makes the push wait for
that answer.

Measured this session: with a `pgserver` instance and `alembic upgrade head`, the
same suite is **660 passed, 0 skipped**, in 88 seconds. The cost of closing this
is 88 seconds.

## OPS-02 · LOW · The documented toolchain cannot run the test suite — **verified**

`AGENTS.md` and `batch-verify.md` both direct local runs at
`/Users/craigrobinson/app-starter/apps/api/.venv`. That venv has no Pillow, so
collection fails outright:

    ModuleNotFoundError: No module named 'PIL'
    !!!! Interrupted: 10 errors during collection !!!!

Pillow arrived with Batch 44's avatar re-encoder. Ten test modules — including
`test_auth`, `test_picks_flow` and `test_health` — cannot even be collected on
the toolchain the docs name. Anyone following `AGENTS.md` today gets a red suite
that says nothing about their change.

A dedicated venv built from `apps/api/requirements-dev.txt` fixes it and has a
second benefit the docs currently apologise for: it pins ruff 0.5.4 and mypy
1.11.0 exactly, closing the divergence `batch-verify.md` devotes four paragraphs
to explaining. Both passed clean on the pinned versions this session.

## OPS-03 · LOW · `.launch-private/` holds plaintext secrets in the working tree

`bf_pass.txt`, `bf_app_key.txt`, `odds_provider_key.txt`,
`production-db-password.txt`, `betfair-client.key` and the VAPID contact all sit
unencrypted in the repository directory. It is gitignored and never committed,
and these files were not read during this review.

It is still a plaintext credential store on a laptop, and one of those
credentials — the odds-api.io key — is the one Batch 36 found leaking into
Railway's logs and recorded as still needing rotation. **Rotating it remains an
owner action and this review did not perform it.**

## OPS-04 · ~~LOW~~ → INFO · The service worker's three-second budget is fine — measured

`apps/web/src/sw.ts:42-44` wraps `/api/v1/` GETs in `NetworkFirst` with
`networkTimeoutSeconds: 3`, falling back to a cache of at most 80 entries held for
an hour. This was written up as too tight for a phone on mobile data against a
Railway service that can cold-start.

**Then it was measured, and it is not.** Twelve samples against production
`/api/v1/health`, plus three forcing a fresh TLS handshake (which is what a cold
app open does):

    warm            88 ms – 306 ms
    fresh TLS      107 ms – 521 ms
    budget        3000 ms

Worst observed is a sixth of the budget. The service is not cold-starting either,
and that is not luck: `run_connection_warmup` runs every ten minutes precisely to
keep a pooled connection hot, and the numbers say it works.

A phone on poor mobile data adds round-trip latency on top, so the margin is
smaller than it looks from a fixed line — but it is a margin, and past the timeout
the member gets cached content rather than an error whenever a cache entry exists.

**No change recommended.** Recorded as a correction to this review rather than
quietly dropped: the original finding reasoned from "Railway can cold-start"
without checking whether this one does.

## OPS-05 · Deploy asymmetry is real and already bit once

Recorded here because it shaped several batch scope decisions rather than because
it is new. Vercel deploys the web app on every push to `main`; the API only moves
when `/ship-prod` runs. On 2026-08-06 that left the API thirteen batches behind
and broke the Coupon tab. `scripts/check-deploy-drift.sh` exists precisely to
surface it and is the right answer.

At the start of this session the API was three commits behind (Batches 49, 51,
53). It was shipped in a separate session during the review and read `in sync` at
`308bc163` afterwards.

**Consequence for every batch specified from this review:** any new API field
must be optional on the client, exactly as Batches 38, 41, 48 and 53 all record,
because there is a window in which the web half is live and the API half is not.

## OPS-06 · LOW · `apps/web/.env.local` points at a different project's API

It reads `VITE_API_URL=https://wc2026-api-production-a0f4.up.railway.app` — the
World Cup predictor's backend, not The Coupon's. Anyone starting the dev server
without noticing is developing against the wrong product's API. A committed
`.env.example` for the web app, or a comment, would stop it.

## Not assessed

- **Load and concurrency.** APScheduler runs in-process on a single Railway
  replica by deliberate design (`LAUNCH_PLAN.md`), which means the API cannot
  scale horizontally without duplicating scheduled work. Nothing here measures
  what one replica does under a real Saturday.
- **Backup and restore.** `docs/runbooks/backup-restore.md` exists and
  `scripts/agent/l3-restore-rehearsal.py` rehearses it, but production has **no
  restore point** under the owner's 2026-07-30 deferral, and `ship-prod.md`
  requires a written forward recovery plan for any migration instead. That
  constraint governs every migration specified from this review.
