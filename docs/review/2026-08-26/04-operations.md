# 04 — Operations, tooling and the gate (follow-up review, 2026-08-26)

Follow-up to `docs/review/2026-08-22/04-operations.md` at commit `308bc16`.
Covers everything shipped since — 79 commits, Batches 54-81 — plus the two
open items carried forward for a spot check. Numbering continues from the
prior review's register (OPS-01..OPS-06); new findings start at OPS-07.

## Carried forward — spot-checked, unchanged

**OPS-03 · `.launch-private/` still holds plaintext secrets, still gitignored.**
`.gitignore:66` still lists `.launch-private/`. The directory still exists with
`bf_pass.txt`, `bf_app_key.txt`, `odds_provider_key.txt`,
`production-db-password.txt`, `betfair-client.key`, `vapid_contact_email.txt`
and others, unencrypted, on the laptop. Not read. Still an owner call; still
carries the odds-api.io key flagged for rotation since Batch 36.

**OPS-06 · `apps/web/.env.local` still points at another product's API.**
`apps/web/.env.local:1` is unchanged: `VITE_API_URL=https://wc2026-api-production-a0f4.up.railway.app`
— the World Cup predictor's backend. No `.env.example` has been added to
`apps/web/` since the last review; the only file matching `.env*` there is
`.env.local` itself. Still local-dev-only impact, still open.

## New findings

### OPS-07 · MED · The runtime dependency advisory count dropped from 29 to 4, but two are unpatched at the pinned major and one is newly reachable

`SEC-09` from the prior review closed its "framework deferred" half: Batch 61
(`a5966af`) raised `fastapi` 0.111.0 → 0.141.1, `starlette` 0.37.2 → 1.6.0,
`pydantic` → 2.13.4 — exactly the trio the prior review recorded as owing a
`/ship-prod`, and `check-deploy-drift.sh` (per the user, already run) confirms
production is caught up. `apps/api/requirements.txt:43,51,99,135` show the new
pins; `scripts/ci-local.sh` prints `fastapi 0.141.1 · starlette 1.6.0` on every
run, so the version the gate checks is the version that ships.

Re-running the audit against the *current* pins finds the advisory count is
down from 29 to a real 4, but they are not all hygiene this time:

```
$ VENV=~/.cache/the-coupon/ci-local-venv; uv pip install --python "$VENV/bin/python" pip-audit
$ "$VENV/bin/pip-audit" -l --desc
Found 4 known vulnerabilities in 2 packages
cryptography       48.0.1  PYSEC-2026-3552  fix 50.0.0  Bleichenbacher oracle in PKCS#7 decrypt
cryptography       48.0.1  PYSEC-2026-3553  fix 49.0.0  exponential-blowup DoS in cert chain building
cryptography       48.0.1  PYSEC-2026-3554  fix 49.0.0  wildcard SAN escapes a name-constrained sub-CA
pydantic-settings  2.13.0  GHSA-4xgf-cpjx-pc3j  fix 2.14.2  symlinked secrets_dir escapes and bypasses the size cap
```

Reachability, checked against the actual call sites (`grep -rn "x509\|pkcs7\|secrets_dir" apps/api/src`
returns nothing outside `.mypy_cache`): the app never parses PKCS#7, never
verifies an x509 chain, and `config.py:72` sets `SettingsConfigDict(env_file=".env", ...)`
with no `secrets_dir` anywhere — so, like the prior review's SEC-09 packages,
all four are currently unreachable. What's new is *why they can't be closed
by version bump alone*: `cryptography` is deliberately capped at 48.0.1 by
`scripts/ci-local.sh:64-75`'s own comment — 49.0.0 is "where macOS wheels stop
entirely," and three of the four CVEs above are only fixed at 49.0.0/50.0.0.
Closing them means either accepting a source build with a Rust toolchain on
every contributor's Mac, or moving CI/local dev off macOS wheels. This is a
real constraint, not neglect, but it means the cryptography advisories the
prior review closed once (Batch 59, 46.0.3 → 48.0.1) have *already* reopened
one release cycle later, on the same package, for the same wheel reason. Worth
a standing line in `requirements.in`'s comment (there's already a paragraph
there explaining the cap) noting that 49.0.0+ is also the fix for these three
CVEs, so the next person who reconsiders the cap has the trade-off in one
place instead of two.

**Suggested fix:** no urgent action (all four unreachable); add the CVE↔wheel
cross-reference to the `requirements.in` comment; revisit if `cryptography`
ships macOS wheels again or a Rust toolchain becomes acceptable in CI.

### OPS-08 · MED · `react-router-dom` carries an open-redirect advisory with no fix in the pinned major, and the app's own guard against it does not close the newer bypass

`apps/web/package.json` pins `react-router-dom": "^6.24.1"`, resolved to
`6.30.3` in the lockfile. `pnpm --dir apps/web audit --prod` reports 9
advisories (3 high, 6 moderate); the two high ones (`nanoid`, `postcss`) are
dev-only, transitive through `tailwindcss-animate` → `tailwindcss` →
`postcss`/`postcss-import`, and never reach the shipped bundle. The `react-router`
set is different — it's a runtime dependency actually exercised by the SPA:

```
moderate  React Router: Open redirect leading to XSS
          react-router-dom  6.30.2 - 6.30.4   Patched versions: <0.0.0
          https://github.com/advisories/GHSA-jjmj-jmhj-qwj2

moderate  React Router's same-origin redirect with path starting // causes
          open redirect via protocol-relative URL reinterpretation
          @remix-run/router 1.3.0-1.23.2, react-router 6.7.0-6.30.3
          https://github.com/advisories/GHSA-2j2x-hqr9-3h42

moderate  React Router: Open redirect via backslash in <Link> and useNavigate
          (CVE-2025-68470 bypass)
          react-router  6.0.0 - <7.18.0
          https://github.com/advisories/GHSA-wrjc-x8rr-h8h6
```

`Patched versions: <0.0.0` on the first one means exactly what it says: there
is no fix released on the 6.x line, only on 7.18.0+. That's a major-version
migration, not a patch bump.

The prior review's SEC-10 voided a *different* open-redirect concern on the
grounds that `_slugify` reduces slugs to `[a-z0-9-]`, so no backslash could
reach a `navigate()` target through that path. That reasoning does not cover
this one. `apps/web/src/pages/LoginPage.tsx:37-40` and
`apps/web/src/pages/RegisterPage.tsx:57-60` both take an unauthenticated,
attacker-suppliable `?next=` query parameter and guard it identically:

```ts
const requested = new URLSearchParams(location.search).get('next');
const destination = requested?.startsWith('/') && !requested.startsWith('//')
  ? requested
  : '/';
navigate(destination, { replace: true });
```

This blocks the classic `//evil.com` protocol-relative payload, but CVE-2025-68470's
bypass is specifically the backslash form — `/\evil.com` — which *does* start
with `/` and does *not* start with `//`, so it passes this guard unchanged.
Per the WHATWG URL spec, browsers treat `\` as `/` inside a "special" scheme
(http/https), so `/\evil.com` resolves to `https://evil.com/`, not a same-origin
path. This was not stress-tested live against a browser (would need Playwright
against a built preview; not run here to keep this session's scope to
verification, not a fix), so treat the mechanism as documented-and-plausible
rather than confirmed exploited — but the code-level fact is not in question:
the guard checks for `//` and not for `/\`, which is exactly the gap the
advisory names.

An attacker would need a victim to click a crafted link such as
`https://the-coupon.example/login?next=/\evil.com` — plausible for a
private-app phishing attempt, since the link's visible host is the real app.

**Suggested fix:** harden the two guards to also reject a destination whose
second character is `\`, or resolve `destination` through
`new URL(requested, location.origin)` and compare `.origin` to
`location.origin` before navigating — cheaper than the framework migration and
closes the actual gap regardless of what react-router does upstream. The
major-version migration to react-router 7 is the complete fix but is out of
proportion to this specific gap and has its own blast radius (data routers,
loader API) worth scoping separately.

### OPS-09 · LOW · `AGENTS.md` undercounts the gate by one check

`AGENTS.md:63` says the default `scripts/ci-local.sh` run is "Ten checks, no
skips." Run both ways this session:

```
$ SKIP_PROD_BUNDLE=1 scripts/ci-local.sh   → ci-local: PASS (10 checks)
$ scripts/ci-local.sh                      → ci-local: PASS (11 checks)
```

The default (no `SKIP_PROD_BUNDLE`) run — which is what CI actually runs, via
its separate `prod-bundle` job in `.github/workflows/ci.yml` — is 11 steps:
ruff check, ruff format, mypy, alembic+pytest, deployment-config assertions,
pnpm install, lint, typecheck, test, build, and the Playwright deep-link
smoke. "Ten" only matches when `SKIP_PROD_BUNDLE=1` is set to drop the
slowest job — the opposite of the no-args case the sentence describes. Both
runs passed clean this session with **zero skips** either way, so this is a
one-off-by-one in the doc, not a gate regression — but it is exactly the kind
of drift OPS-01/OPS-02 were about, so worth a one-word fix (`Eleven checks,
no skips` for the default, or state the ten-check count against
`SKIP_PROD_BUNDLE=1` explicitly).

**Suggested fix:** correct the count in `AGENTS.md:63`.

### OPS-10 · INFO · The aggregate rate-limit gap (CORR-03) is unchanged, and public signup made the arithmetic worse, not just more likely

The prior review's CORR-03 recorded a per-member fix (`PICK_SUBMIT_LIMIT =
10/hour`, Batch 57) with the aggregate gap left open and stated in a test.
That test is unchanged and still red-if-fixed:

`apps/api/tests/test_request_budget.py:286-301`,
`test_the_pick_path_is_not_bounded_in_total_and_this_is_known`:

```python
league_max_members = 15  # `leagues.max_members` default
worst_case = _pick_submit_limits()["hour"] * league_max_members
assert worst_case > HOURLY_LIMIT, (
    "a per-member limit now bounds the aggregate — if this fails the gap has "
    "been closed and this test should be replaced by one asserting the real "
    "bound"
)
```

`STATUS.md:49` states the same thing in prose: "The aggregate is still
unbounded — fifteen members at ten each exceeds the plan — and that gap is
stated in a test rather than left to be rediscovered." Nothing since Batch 57
touches it; `consume_shared_limit` (the mechanism named as the fix, already
used by the populate path — `apps/api/src/routers/leagues.py:122`,
`apps/api/src/routers/admin.py:814`) has not been wired into the pick-submit
path.

What's changed since the prior review is exposure, not the mechanism.
`max_members` has always allowed up to 50
(`apps/api/src/routers/leagues.py:326,354` — `Field(default=15, ge=2, le=50)`,
unchanged since Batch 1/15), so the worst case was never bounded at 15 — the
test's own default is illustrative, not a ceiling. At the *actual* ceiling,
`10/hour × 50 members = 500/hour` against a 100/hour provider plan is a 5x
overshoot, not the 1.5x the 15-member test states. Batch 63 (`fbb0403`, this
session's window) opened public self-serve registration — `POST
/auth/register`, unauthenticated, no invite — which is the thing that makes a
league actually reaching towards that ceiling a live possibility rather than
a hypothetical one; before Batch 63 every member was hand-provisioned by the
owner, so the practical membership count was bounded by how many invites the
owner minted.

This is not a new gap and not mis-scoped by the prior review — it was
correctly recorded as open with the reasoning stated. It is re-flagged here
because the precondition the owner would use to decide urgency (how many
members a league can realistically reach) changed materially in the window
this follow-up covers, and the fix already has a named mechanism
(`consume_shared_limit`) sitting unused beside the exact code path that needs
it.

**Suggested fix:** unchanged from the prior review — wire `consume_shared_limit`
into the pick-submit path, plus the owner's decision on what a member sees
when the shared bucket is empty (a pick cannot fall back to a stale price;
`picks.py:72` documents why). Product decision, not a mechanical fix.

## Confirmed clean

- **CI/gate integrity (item 2).** `scripts/ci-local.sh` was run twice this
  session, once with and once without `SKIP_PROD_BUNDLE`. Both passed with
  zero skips and zero failures across all backend, deployment-config, and
  frontend checks, including a real `pgserver` PostgreSQL run of the full
  suite via `alembic upgrade head + pytest`. No step has quietly regressed to
  a conditional skip since the prior review's OPS-01/OPS-02 fixes (Batch 60).
- **Migration hygiene (item 4).** `migrations/versions/001_baseline.py`
  through `016_nullable_pin_hash.py` form a single linear chain — every
  `down_revision` points at exactly the prior file's `revision`, no branches,
  no gaps — and every one of the 16 migrations defines a `downgrade()`. No
  out-of-order or missing-downgrade issues found.
- **Scheduler jobs (item 3).** `apps/api/src/scheduler.py:497-630` lists ten
  jobs; cross-checked against Batch 75's removal of the nightly `pg_dump`
  (`d012ebf`, "stop dumping the whole database to a tmpfs every night" — it
  wrote to `/tmp` on a service with no mounted volume, so every dump was lost
  on the next redeploy and was contributing zero recovery value while still
  costing Supabase egress, part of what tripped the `exceed_egress_quota`
  incident this environment's own memory records). The job is fully gone, not
  merely disabled, and `docs/runbooks/backup-restore.md` was already
  consistent with removing it (it named Supabase managed backups/PITR as the
  actual source of record). Batch 76's three notification triggers
  (`dc4fe16`) reuse the existing `pick_reminders`/`open_gameweeks`/
  `lock_gameweeks` cron slots at staggered minutes (`:15`, `:01`, `:00`) with
  an explicit comment about why, rather than adding an unstaggered fourth job.
- **Deploy docs vs. env vars (item 3).** `docs/agent-commands/ship-prod.md:47-50`
  already lists `VAPID_CONTACT_EMAIL`, `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`
  among the required Railway variables, and `VITE_VAPID_PUBLIC_KEY` for Vercel
  (step 6). These were added at `af9c20c` (L4 production infrastructure),
  which predates this review's whole window — so Batch 76's notification
  triggers reused push infrastructure that was already provisioned and
  already documented; no new env var was needed or missed.
- **Housekeeping.** No `TODO`/`FIXME`/`XXX` markers found in `apps/api/src`,
  `apps/web/src`, `scripts/`, or `docs/agent-commands/`. `scripts/agent/`
  holds three still-referenced scripts (`l3-logical-backup.py`,
  `l3-restore-rehearsal.py`, `batch-start.sh`/`batch-verify.sh` wrappers), no
  orphaned scripts found.

## Not assessed

Same boundaries as the prior review: no load/concurrency testing, no live
provider verification, and this session did not run a live-browser check of
OPS-08's redirect mechanism (documented as plausible from the code and the
advisory text, not click-tested).
