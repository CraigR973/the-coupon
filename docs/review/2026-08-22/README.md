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

Ordered by what I would fix first. "Batch" is the row added to
`docs/BUILD_PLAN.md` for it.

| id | sev | finding | batch |
| --- | --- | --- | --- |
| UX-01 | CRITICAL | `user-scalable=no` disables pinch-zoom app-wide (WCAG 1.4.4) | 55 |
| SEC-01 | HIGH | changing a PIN revokes no session | 56 |
| SEC-02 | HIGH | the PIN reset flow notifies nobody; the message is untrue | 56 |
| UX-02 | HIGH | light theme muted text fails AA on every surface | 54 |
| SEC-09 | HIGH | 29 advisories in runtime deps (starlette, cryptography) | 59 |
| CORR-01 | MED | two endpoints answer 500 to a malformed UUID | 57 |
| SEC-03 | MED | `X-Forwarded-For` trusted from the left; IP limits bypassable | 58 |
| SEC-04 | MED | lockout never decays — a forgotten PIN locks out permanently | 58 |
| UX-03 | MED | dark muted text fails on the two upper surface tiers | 54 |
| UX-04 | MED | form disclosure is 70x22 — under WCAG 2.2 SC 2.5.8 | 55 |
| SEC-05 | MED | no refresh-token reuse detection | 58 |
| SEC-06 | MED | correlation ID unvalidated, unbounded, reflected | 58 |
| CORR-02 | MED | lock is checked before the provider call, not after | 57 |
| CORR-03 | MED | a pick can outspend the provider's hourly budget | 57 |
| OPS-01 | MED | the local gate skips 151 tests and close-out does not wait for CI | 60 |
| SEC-10 | MED | react-router open-redirect advisory affects a runtime dep | 59 |
| OPS-02 | LOW | the documented toolchain cannot run the suite | 60 |
| SEC-07 | LOW | `refresh_tokens` is append-only and never pruned | 58 |
| SEC-08 | LOW | no weak-PIN policy | 58 |
| SEC-11 | LOW | no `Cache-Control: no-store` on authenticated JSON | 58 |
| OPS-03 | LOW | `.launch-private/` holds plaintext secrets in the working tree | — owner |
| OPS-04 | LOW | service worker gives the API a 3s network timeout | 60 |
| UX-05 | LOW | the home screen is one card and ~900px of nothing | — deferred |
| UX-06 | LOW | four info blocks before the first fixture | — deferred |

## Two things this review did not do

- **No load or performance testing.** Nothing here says how the app behaves
  under concurrent Saturday traffic; the single Railway replica and the
  in-process APScheduler make that worth its own exercise.
- **No live provider verification.** `AGENTS.md` reserves the real slate and
  pricing check for the owner, and this review honoured that throughout.
