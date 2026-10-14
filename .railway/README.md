# Railway configuration

`.railway/railway.ts` is the deployment configuration for the `api` service in
both recorded Coupon Railway projects. It is a named partial so it cannot delete
resources owned outside this repository, and it rejects every unrecorded
project/environment pair.

It also declares the `payments` service (Batch 207, ADR 0009 option B), switched off
per project in `PAYMENTS_SERVICE_ENABLED`. A switched-off project's graph holds `api`
alone, so no plan creates it. The owner creates the service, seals its variables and
gives it a domain; one commit then sets the project's switch to `true` and records
its origin in `PAYMENTS_ORIGINS`, and `scripts/assert-deployment-config.py`'s
`EXPECTED_PAYMENTS_ENABLED` moves with it.

Install the pinned SDK with the repository dependencies:

```bash
pnpm install --frozen-lockfile
```

`railway config plan` is read-only, but it still needs an exact target. Set
`RAILWAY_PROJECT_ID`, `RAILWAY_ENVIRONMENT_ID`, and `RAILWAY_SERVICE_ID` to the
recorded target from `docs/agent-commands/ship-staging.md` or
`docs/agent-commands/ship-prod.md`; never rely on the ambient repository link.
The Railway CLI's TypeScript evaluator also requires Node 22 or newer; the web
application's own toolchain is Node 24.

Do not run `railway config apply` as a batch step. The matching ship workflow
reviews and applies a pinned, non-destructive plan immediately before the source
upload. It also verifies that no legacy Railway Config File setting can compete
with the IaC graph.

Railway treats service variables as a complete set. The file declares every
known staging/production variable with `preserve()` so values remain sealed. Add
any new live variable name to `PRESERVED_VARIABLE_NAMES` before applying again;
the ship workflow refuses destructive plans rather than deleting an omission.
