# The Coupon — launch log

Launch-phase close-out entries are appended here by the explicit
`/launch-closeout <L0-L5>` workflow. Build-batch history remains in
`session-log.md`.

## L0 — Owner decisions and project identity
**Commits:** 4194705, f2a1b06 · verified: GREEN owner, repository, hostname,
budget, roster, and connector gates

### Key facts for future sessions
- `origin` is the public `CraigR973/the-coupon` repository; the owner explicitly
  chose public visibility after private Actions jobs hit account billing limits.
- Staging and production use fresh Supabase, Railway, and Vercel targets under
  the recorded owner accounts; discovered WC2026 and Garmin targets are
  excluded.
- MVP hostnames are platform-assigned; custom-domain and DNS spend is USD 0.
- The administrator is Craig and the initial roster count is 15; the other
  display names and all PIN handoff remain out of band.
- Sentry is omitted; MVP monitoring uses Railway and Vercel platform logs.
- Supabase MCP is docs-only until L2 can scope it read-only to the fresh
  staging ref; production must never be connected.

**Next:** L1 — Launch-hardening implementation

## L1 — Launch-hardening implementation
**Commits:** 51e2a52, af7eb62, 0e889f2, d5a2273, e2740f8 · verified: GREEN
local backend, frontend, clean
PostgreSQL, Railway/Nixpacks config, and production-bundle gates

### Key facts for future sessions
- Railway backend builds from the repo root with Nixpacks; local Docker Desktop
  is not required.
- Production startup applies `alembic -c apps/api/alembic.ini upgrade head`
  before Uvicorn and checks `/api/v1/health/ready`.
- Public avatar upload, browser Supabase, passwordless activation, public reset
  tokens, and Sentry surfaces were removed for MVP launch.
- Production rejects fake odds mode; staging can explicitly use `FakeBetfair`.
- The owner-only live Betfair account/slate check remains deferred to L4.
- L1 verification used clean `pgserver` PostgreSQL through migration revision
  `003`.

**Next:** L2 — Fresh staging infrastructure

## L2 — Fresh staging infrastructure
**Commits:** 40be573 · verified: GREEN local backend, frontend, clean
PostgreSQL, Supabase lockdown, Railway topology/readiness, Vercel SPA, and
staging data-isolation gates

### Key facts for future sessions
- Supabase staging is `gegcnhoeudpkcoxqcebe` in London on the Free plan; it is
  at migration `004`, and its public schema and Data API are locked down.
- Railway staging is one always-on, resource-capped Amsterdam `api` replica at
  `https://api-production-0641.up.railway.app`, with the scheduler and
  `FakeBetfair` enabled.
- Vercel staging uses project `prj_r9VsE4xnCj53S3OiOUH7GSzQsn2c`, the
  `apps/web` root, and `https://the-coupon-staging.vercel.app`.
- Staging contains 15 synthetic profiles and memberships, with no real member
  data, production credentials, or owner Betfair credentials.
- The target-specific `/ship-staging` workflow records exact deployment,
  health, migration, smoke, and rollback checks.
- Node.js 20 Vercel builds expire after 2026-10-01; runtime migration remains
  follow-up work.

**Next:** L3 — Staging verification

## L3 — Staging verification
**Commits:** 53334a1, 0e88d03 · verified: GREEN CI, canned-odds browser
story, phone push, scheduler, platform logs, disposable restore, and rollback

### Key facts for future sessions
- The reviewed forward staging source is `9f498675`; Railway is restored to
  deployment `900b74fa-80cd-40d7-9a3a-5eba472f0fc6`, and Vercel is restored
  to `dpl_smnv3fDEV1EPYpyR2TDA56maiykS`.
- The full synthetic browser story passed, including durable lockout,
  membership administration, unique picks, lock, settlement retry, standings,
  combined coupon, and a rollback-backed PWA update.
- The owner confirmed push subscribe, test delivery, and unsubscribe on a
  supported phone; zero subscriptions remained active afterward.
- One always-on Railway replica exercised every scheduler path, including the
  corrected PostgreSQL 17 backup and connection warmup.
- The approved logical export restored into disposable PostgreSQL at migration
  `004` with representative row counts matching staging.
- Final bounded Railway and Vercel reviews found no application errors,
  secrets, credentials, PIN values, tokens, or synthetic profile names.

**Next:** L4 — Fresh production infrastructure and owner checks

## L4 — Fresh production infrastructure and owner checks
**Commits:** af9c20c · verified: GREEN provisioning, lockdown, deployment,
bootstrap, TLS/CORS, and logs — RED live Betfair slate, carried to Batch 7

### Key facts for future sessions
- Supabase production is `pugujiiojitstkilphrz` (London, Free plan, sole active
  Coupon project) at migration `004`; staging `gegcnhoeudpkcoxqcebe` is paused
  to free the two-active-project quota and is restorable for 90 days.
- Railway reaches Supabase over the **direct** IPv6 endpoint; an IPv4
  workstation must use the session pooler at
  `aws-1-eu-west-2.pooler.supabase.com` as `postgres.<ref>` — note `aws-1`,
  not `aws-0`.
- **Betfair cannot be used from Railway at all.** Production login returns
  `BETTING_RESTRICTED_LOCATION`; Railway serves only the Netherlands, the USA,
  and Singapore, and Betfair Exchange is unavailable in all three. The same
  credentials succeed from a UK machine.
- Three Betfair defects were found by probing the live API, none by tests:
  certlogin returns `sessionToken`/`loginStatus`; the English divisions carry
  sponsored names; and a fixed division list starved the slate. The slate is
  now chosen by country and kick-off time.
- Launch ships with **no database backup** by owner decision; `picks` has no
  second copy, and migrations apply automatically on boot, so rollback must
  never assume a recoverable database.
- Production holds one bootstrapped administrator with a known PIN that must be
  changed at first login; the roster bootstrap rewrites `pin_hash` for every
  entry on each run, so members added later lose self-chosen PINs.

**Next:** Batch 7 — replace the Betfair Exchange with odds-api.io priced by
Bet365, which is now required for production to obtain odds at all
