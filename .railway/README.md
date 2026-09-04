# Railway configuration

`.railway/railway.ts` is the deployment configuration for the `api` service in
both recorded Coupon Railway projects. It is a named partial so it cannot delete
resources owned outside this repository, and it rejects every unrecorded
project/environment pair.

Install the pinned SDK with the repository dependencies:

```bash
pnpm install --frozen-lockfile
```

`railway config plan` is read-only, but it still needs an exact target. Set
`RAILWAY_PROJECT_ID`, `RAILWAY_ENVIRONMENT_ID`, and `RAILWAY_SERVICE_ID` to the
recorded target from `docs/agent-commands/ship-staging.md` or
`docs/agent-commands/ship-prod.md`; never rely on the ambient repository link.
The Railway CLI's TypeScript evaluator also requires Node 22 or newer even
though the web application remains on Node 20.

Do not run `railway config apply` as a batch step. The matching ship workflow
reviews and applies a pinned, non-destructive plan immediately before the source
upload. It also verifies that no legacy Railway Config File setting can compete
with the IaC graph.

Railway treats service variables as a complete set. The file declares every
known staging/production variable with `preserve()` so values remain sealed. Add
any new live variable name to `PRESERVED_VARIABLE_NAMES` before applying again;
the ship workflow refuses destructive plans rather than deleting an omission.
