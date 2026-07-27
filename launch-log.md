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
**Commits:** 51e2a52 · verified: GREEN local backend, frontend, clean
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
