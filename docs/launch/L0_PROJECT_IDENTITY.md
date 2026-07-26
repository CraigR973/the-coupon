# L0 — project identity and owner decisions

Recorded: 2026-07-26

This is the source of record for launch target selection. The owner's
instruction to implement L0 accepts the default MVP scope in
`docs/LAUNCH_PLAN.md`. It does not authorize a domain purchase, a paid project,
a deployment, a database mutation, a real Betfair login, or member invitations.
Those actions remain limited to their later launch phases.

Owner decisions recorded on 2026-07-26:

- administrator display name: `Craig`;
- initial roster: 15 profiles and 15 league memberships, including Craig;
- Sentry: omitted from the MVP.

## MVP scope

The launch keeps the seven defaults in `docs/LAUNCH_PLAN.md`:

1. Supabase is PostgreSQL only; incomplete avatar upload and dead Supabase
   application configuration are removed in L1.
2. Push remains, with the web settings aligned to global mute and quiet hours.
3. Web and API use separate, explicit HTTPS origins.
4. Passwordless device activation is removed; display name plus PIN remains.
5. L1 adds an admin-operated one-time PIN reset that does not log secrets.
6. The scheduler remains embedded in exactly one always-on Railway replica,
   with settlement retries added in L1.
7. MVP monitoring uses Railway and Vercel platform logs; Sentry is omitted.

## Ownership and fresh target names

Ambient authentication was used only to identify owner-controlled accounts.
No existing project was selected as a Coupon target.

| System | Selected owner | Fresh Coupon targets | Provisioning phase |
| --- | --- | --- | --- |
| GitHub | Personal account `CraigR973` | Private repository `CraigR973/the-coupon` | Created in L0 |
| Supabase | `CraigR973's Org` (`eufhjqkyoiuzfwuptlyn`) | `the-coupon-staging`, `the-coupon-production` | L2, L4 |
| Railway | `Craig Robinson's Projects` (`518ea7c5-7ee6-464b-bcf0-befed3153c1f`) | Projects `the-coupon-staging`, `the-coupon-production`; service `api` in each | L2, L4 |
| Vercel | `craigr973's projects` (`team_MVQMOaFtYHlwO5QVzSOZQ0Ud`) | Projects `the-coupon-staging`, `the-coupon-production` | L2, L4 |
| Betfair | Owner account only; agents may not log in | Delayed/read-only app identity for production only; staging uses `FakeBetfair` | Owner action in L4 |

The following discovered resources are explicitly excluded:

- Supabase refs `lesscrmlfijiokureomm` (`wc2026-staging`),
  `kznxjyaanotrejcevngy` (`wc2026-predictor`), and
  `pzqmswvozjnkxbqqowuj` (`CraigR973's Project`).
- Every existing Railway project, including `garmin-coach` and
  `wc2026-api-prod`.
- Every existing Vercel project, including Garmin and WC2026 projects.

Fresh Supabase and hosting project IDs must be appended here when L2 and L4
create them. Names alone never authorize a connector or CLI target.

## Repository and integration

- `origin` is `https://github.com/CraigR973/the-coupon.git`.
- GitHub reports the repository as private and empty as of 2026-07-26.
- L0 verification must not push.
- All launch phases integrate through pull requests and the required
  `Quality / backend` and `Quality / frontend` checks. A phase is not merged
  while either check is missing or failing.
- L0 close-out is the one-time bootstrap: it first pushes the unchanged,
  pre-L0 local `main` to the verified empty private remote, then pushes the L0
  branch and follows the same pull-request path. No implementation is pushed
  directly to `main`.
- Close-out bookkeeping is committed on the phase branch before its pull
  request, as defined by the canonical `/launch-closeout` workflow. After merge,
  local `main` is fast-forwarded to the remote result.
- Force pushes, direct implementation pushes to `main`, and required-check
  bypasses are prohibited.

## Hostnames

The MVP uses only the no-cost hostnames assigned by Vercel and Railway. No
custom domain will be purchased or configured.

| Environment | Web | API |
| --- | --- | --- |
| Staging | Vercel hostname for `the-coupon-staging` | Railway hostname for the `api` service in `the-coupon-staging` |
| Production | Vercel hostname for `the-coupon-production` | Railway hostname for the `api` service in `the-coupon-production` |

L2 and L4 must record the exact assigned HTTPS hostnames and project/service
IDs immediately after provisioning. The project and service names must not be
changed afterward because those platform hostnames form the MVP's stable public
origin contract. `VITE_API_URL` and `FRONTEND_ORIGIN` must use those exact,
environment-specific origins.

## Regions and time

- Product scheduling and lock rules: `Europe/London`.
- Supabase staging and production databases: `eu-west-2` (London).
- Railway staging and production APIs: one replica in EU West Metal,
  `europe-west4-drams3a` (Amsterdam).
- Vercel web assets: global CDN. The current static Vite frontend has no
  server-function region to configure.

Staging and production use the same regions but separate projects, credentials,
databases, deployment aliases, and domains.

## Budget controls

Coupon-specific recurring infrastructure must remain at or below USD 50 per
month unless the owner explicitly changes this record.

- Supabase: use Pro with Micro compute, keep its spend cap enabled, and stop
  before provisioning if the two Coupon projects would take projected
  Coupon-specific recurring spend above USD 35 per month.
- Railway: use Hobby, set a USD 10 compute alert and USD 15 compute hard limit,
  and disable Railway Agent spending for the Coupon projects.
- Vercel: use its no-cost personal tier for the MVP. Stop if a required setting
  needs a paid plan.
- Sentry: omitted; approved spend is USD 0.
- Domain and DNS budget: USD 0; use platform-assigned hostnames.
- Every provisioning phase must show the current checkout or cost estimate to
  the owner before creating a paid resource. No existing unrelated project's
  budget or quota is treated as Coupon capacity.

## Supabase connector boundary

The former `.codex/config.toml` ref `lesscrmlfijiokureomm` is rejected because
account-level metadata identifies it as `wc2026-staging`. The repository MCP
URL is now restricted to read-only documentation features and has no project
ref. L2 may replace it only with the newly created Coupon staging ref, scoped
read-only. Production must never be connected to an agent MCP server.

## Initial roster handling

Real display names, PINs, reset tokens, phone numbers, and invitation details
must not be committed. The owner supplies the reviewed roster out of band in
`.launch-private/roster.csv`, which is ignored by Git. L1 will provide the
idempotent bootstrap command and a non-secret input template; L4 will record
only the expected 15 profiles and 15 league memberships as verification
evidence.

The administrator display name is `Craig`. The other 14 display names remain
owner-held and will be supplied through the ignored roster file when L4 is
ready.

No initial PINs are needed in L0. They will be generated or entered at
bootstrap and distributed by the owner outside logs, Git, and chat.
