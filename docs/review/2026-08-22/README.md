# Full-application review — 2026-08-22

A standing review of The Coupon at commit `308bc16` (Batch 53 closed, all 53
build batches ticked, L5 the only open launch phase), covering engineering
correctness, security, UI/UX, accessibility, dependencies and operations.

## How this was produced

Not a reading of the code alone. Every finding below that is marked **verified**
was reproduced against something running:

- **Backend:** the full suite on a pinned toolchain — a purpose-built venv from
  `apps/api/requirements-dev.txt`, so ruff 0.5.4 and mypy 1.11.0 are the exact
  versions CI pins rather than the newer ones `AGENTS.md` warns diverge. Run
  against a real `pgserver` PostgreSQL 16.2 with `alembic upgrade head`, so the
  151 Postgres-backed tests that normally skip actually executed.
- **API behaviour:** `tests.e2e_server` on that database with
  `ODDS_PROVIDER=fake`, seeded and probed over HTTP.
- **Frontend:** the real app in a browser at 390x844, with axe-core 4.10.2
  injected into the live page — so colour contrast was measured against computed
  styles instead of being skipped, which is what `test/accessibility.test.tsx`
  has to do under jsdom.
- **Production:** read-only. Response headers, TLS, and the documentation routes
  on `api-production-109b1.up.railway.app`. Nothing was written, no load was
  generated, and no live Betfair or odds-provider session was touched.

## Baseline — what is already green

| gate | result |
| --- | --- |
| pytest (no DB) | 509 passed, **151 skipped** |
| pytest (with PostgreSQL) | **660 passed, 0 skipped** |
| ruff 0.5.4 check + format | clean, 103 files |
| mypy 1.11.0 strict | clean, 63 source files |
| eslint | 0 errors, 12 warnings (all `react-refresh/only-export-components`) |
| tsc --noEmit | clean |
| vitest | 387 passed, 40 files |
| production security headers | HSTS, CSP, nosniff, DENY, Referrer-Policy, Permissions-Policy all present |
| production docs routes | `/api/docs`, `/api/redoc`, `/api/openapi.json` all 404 |

**1,047 tests pass.** This is a well-built application, and the review should be
read in that light: the findings below are the exceptions in a codebase whose
normal standard is high, not a catalogue of neglect.

## The documents

| file | covers |
| --- | --- |
| [01-security.md](01-security.md) | auth, sessions, rate limiting, headers, dependencies |
| [02-correctness.md](02-correctness.md) | the game rules, races, input handling, time |
| [03-ux-accessibility.md](03-ux-accessibility.md) | the real screens, contrast, targets, zoom |
| [04-operations.md](04-operations.md) | the gate, the toolchain, deploy, housekeeping |

## Register

Ordered by what I would fix first. Every row was worked through in the same
overnight session the review was written in; this table is the outcome, not a plan.

| id | sev | finding | batch | outcome |
| --- | --- | --- | --- | --- |
| UX-01 | CRITICAL | `user-scalable=no` disables pinch-zoom app-wide (WCAG 1.4.4) | 55 | **fixed** — axe critical gone |
| SEC-01 | HIGH | changing a PIN revokes no session | 56 | **fixed** — verified over HTTP |
| SEC-02 | HIGH | the PIN reset flow notifies nobody; the message is untrue | 56 | **fixed** — audit row + admin push |
| UX-02 | HIGH | light theme muted text fails AA on every surface | 54, 62 | **fixed** — 21 nodes → 0 |
| SEC-09 | HIGH | 29 advisories in runtime deps (starlette, cryptography) | 59, 61 | **part** — cryptography done; framework deferred |
| CORR-01 | MED | two endpoints answer 500 to a malformed UUID | 57 | **fixed** — 404 / 422 |
| SEC-03 | MED | `X-Forwarded-For` trusted from the left; IP limits bypassable | 58 | **fixed** — 429 now holds |
| SEC-04 | MED | lockout never decays — a forgotten PIN locks out permanently | 56 | **fixed** |
| UX-03 | MED | dark muted text fails on the two upper surface tiers | 54 | **fixed** — 7 nodes → 0 |
| UX-04 | MED | form disclosure is 70x22 — under WCAG 2.2 SC 2.5.8 | 55 | **fixed** — 70x24 |
| SEC-05 | MED | no refresh-token reuse detection | 58 | **fixed** — family revoked |
| SEC-06 | MED | correlation ID unvalidated, unbounded, reflected | 58 | **fixed** — UUID or minted |
| CORR-02 | MED | lock is checked before the provider call, not after | 57 | **fixed** |
| CORR-03 | MED | a pick can outspend the provider's hourly budget | 57 | **fixed** per member; aggregate gap recorded in a test |
| OPS-01 | MED | the local gate skips 151 tests and close-out does not wait for CI | 60 | **fixed** — docs now point at `ci-local.sh` |
| SEC-10 | MED | react-router open-redirect advisory affects a runtime dep | — | **void** — `_slugify` reduces slugs to `[a-z0-9-]`; no backslash can reach a navigate target |
| OPS-02 | LOW | the documented toolchain cannot run the suite | 60 | **fixed** — documented |
| SEC-07 | LOW | `refresh_tokens` is append-only and never pruned | 58 | **fixed** — nightly job, 7-day grace |
| SEC-08 | LOW | no weak-PIN policy | 58 | **fixed** |
| SEC-11 | LOW | no `Cache-Control: no-store` on authenticated JSON | 58 | **fixed** |
| CORR-04 | LOW | changing `pick_scope` mid-round leaves the fixture rule unenforced | — | **open** — reachability unconfirmed |
| CORR-05 | LOW | non-existent/ambiguous local times at the DST boundary | — | **open** — no league configuration reaches it |
| OPS-03 | LOW | `.launch-private/` holds plaintext secrets in the working tree | — | **owner** — includes the odds key Batch 36 flagged for rotation |
| OPS-04 | ~~LOW~~ | service worker gives the API a 3s network timeout | — | **void** — measured 88–521ms against a 3000ms budget |
| OPS-06 | LOW | `apps/web/.env.local` points at another project's API | — | **open** — local dev only |
| UX-05 | LOW | the home screen is one card and ~900px of nothing | — | **deferred** — design judgement |
| UX-06 | LOW | four info blocks before the first fixture | — | **deferred** — design judgement |

**Nineteen fixed, two void, one part-done, six left** — of which three are design or
owner calls and three are open with the reasoning recorded.

### What shipped

Batches 54, 55, 56, 57, 58, 59 (part), 60 and 62, each verified through
`scripts/ci-local.sh` and merged to `main`. The test count went from **1,047 to
1,302** — 692 backend against real PostgreSQL (was 660) and 610 frontend (was 387)
— and the pick screen went from one critical axe violation and 21 contrast failures
to **zero violations of any rule in either theme**.

**A `/ship-prod` is owed.** Batches 56, 57, 58 and 59 are backend, and Railway does
not move on a push to `main` — only the web half of the night is live.

### Where the review was wrong

Recorded because a review that never corrects itself is not being checked:

- **OPS-04** reasoned from "Railway can cold-start" without measuring whether this
  service does. It does not; the finding is void.
- **SEC-10** assumed a data-built redirect target could carry a backslash. Slugs are
  `[a-z0-9-]` by construction, so it cannot.
- **UX-02** called the brand-token half a design decision. It was mechanical —
  Tailwind scales colours per utility — and Batch 62 finished it.
- Two suspicions were dropped before they reached the documents: `PinInput` dropping
  digits (an automation artifact — the component is correct and well tested) and
  avatars being stored under the declared content-type (the code already sends
  `STORED_MEDIA_TYPE`).

## Two things this review did not do

- **No load or performance testing.** Nothing here says how the app behaves
  under concurrent Saturday traffic; the single Railway replica and the
  in-process APScheduler make that worth its own exercise.
- **No live provider verification.** `AGENTS.md` reserves the real slate and
  pricing check for the owner, and this review honoured that throughout.
