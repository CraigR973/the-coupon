# The Coupon — launch log

Launch-phase close-out entries are appended here by the explicit
`/launch-closeout <L0-L5>` workflow. Build-batch history remains in
`session-log.md`.

## L0 — Owner decisions and project identity
**Commits:** 4194705 · verified: GREEN owner, repository, hostname, budget,
roster, and connector gates

### Key facts for future sessions
- `origin` is the new private `CraigR973/the-coupon` repository.
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
