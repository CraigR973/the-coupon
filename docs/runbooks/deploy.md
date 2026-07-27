# Deploy Runbook

Use this after L2/L4 provision exact staging or production targets. Do not infer
targets from cached CLI state.

## Backend

1. Confirm the target Railway service name and environment.
2. Confirm exactly one always-on replica and `SCHEDULER_ENABLED=true`.
3. Confirm required secrets are present: `DATABASE_URL`, JWT secrets,
   `ENVIRONMENT`, `FRONTEND_ORIGIN`, VAPID keys, and Betfair settings for
   production.
4. Deploy the repo-root Railway/Nixpacks service.
5. Wait for `/api/v1/health/ready` to pass.
6. Check Railway logs for migration success and absence of PINs, tokens, or
   credentials.

## Frontend

1. Confirm the target Vercel project and `VITE_API_URL`.
2. Deploy `apps/web` using the committed Vercel configuration.
3. Open `/login`, `/forgot-pin`, and a protected deep link such as `/settings`.
4. Confirm the protected deep link refreshes through the SPA and redirects to
   login when unauthenticated.
