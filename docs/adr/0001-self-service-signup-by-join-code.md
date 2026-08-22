# ADR 0001 — Self-service signup by league join code

Status: **superseded by ADR 0008**, 2026-08-22. Never implemented as written.

The problem this ADR identified was real and was fixed; the mechanism below was
not the one chosen. ADR 0008 adds open registration at `POST /auth/register`
rather than gating account creation on a league join code, because the join code
gates league *membership* and that gate already exists. Everything below is
retained as the record of what was considered — the "What already exists"
inventory is still accurate, and the security considerations carried forward
unchanged.

## Context

L0 recorded The Coupon as a private league whose members are provisioned by an
operator. `apps/api/src/seeds.py` states it directly: users are created by an
operator, not through a public signup flow. Three checks confirm the code
matches that decision:

- no `register` or `signup` route exists; `routers/auth.py` exposes only login,
  refresh, logout, profile update, PIN change, and PIN reset request;
- `Profile` rows are constructed in exactly two places, both in `seeds.py`; and
- `POST /api/v1/leagues/join-by-code` takes `player: CurrentUser`, so it joins
  an **existing** account to a league rather than creating one.

The owner expected the flow used by the separate `wc_2026_predictor`
application, where a new member self-registers with a league code. That
application's `routers/auth.py` exposes an unauthenticated `join-by-code` which
creates the `Profile` inline and returns a token pair, logging the member
straight in.

Adding fourteen members through the roster bootstrap works, but every re-run
rewrites `pin_hash` for every roster entry and resets `failed_login_count` and
`locked_until`. Verified on a scratch database: a member's self-chosen PIN
stopped working after an unrelated re-run. Operator provisioning therefore
makes adding a member mid-season disruptive.

## Decision

Add an unauthenticated signup path that creates a profile and joins the league
in one step, keyed on the league's existing join code. Retain the roster
bootstrap for the administrator and for recovery.

This is a deliberate reversal of part of the L0 privacy posture and must be
recorded as such. The league becomes joinable by anyone holding a valid join
code, rather than only by people the operator has provisioned.

## What already exists

Most of the mechanism is present and needs no change:

| Piece | Location |
| --- | --- |
| `leagues.join_code`, `String(8)`, unique, with a Postgres `server_default` of `upper(substr(md5(random()::text), 1, 6))` | `migrations/versions/001_baseline.py` |
| `generate_join_code()` | `apps/api/src/auth.py` |
| `POST /api/v1/leagues/join-by-code` — league lookup, capacity check, duplicate-membership check, membership upsert, audit, notify | `apps/api/src/routers/league_memberships.py` |
| `POST /api/v1/leagues/{slug}/rotate-join-code`, administrator only | `apps/api/src/routers/league_memberships.py` |
| `_resolve_active_membership`, `_active_member_count`, `_upsert_membership`, `_audit`, `notify_member_joined` | `apps/api/src/routers/league_memberships.py` |
| `_issue_token_pair(user, db, device_hint)` returning `(access, refresh)` | `apps/api/src/routers/auth.py` |
| `JoinByCodePage.tsx`, routed at `/leagues/join` | `apps/web/src/pages/`, `apps/web/src/App.tsx` |
| `uq_profiles_display_name` | `migrations/versions/001_baseline.py` |

Because the join code has a database-level default, the league created by the
roster bootstrap already carries a usable code. No migration is required.

## The change

### API

Add `POST /api/v1/auth/join-by-code`, unauthenticated, in `routers/auth.py`
beside the other credential-issuing routes.

Request:

```json
{ "code": "A1B2C3", "display_name": "Alice", "pin": "4821", "timezone": "Europe/London" }
```

Response `201`, identical in shape to login so the client can reuse its
session-establishing path:

```json
{ "access_token": "...", "refresh_token": "...", "player": { "id": "...", "display_name": "Alice" } }
```

Order of operations, failing closed at each step:

1. resolve the league by `join_code` (uppercased); `400` on no match. Return
   the same generic error for an unknown code as for a full league, so the
   endpoint cannot be used to enumerate valid codes;
2. reject if active membership count has reached `league.max_members`;
3. reject a `display_name` that collides case-insensitively with a live
   profile, mirroring `uq_profiles_display_name`. Catch the integrity error as
   well as pre-checking, since two concurrent signups can pass the same check;
4. validate the PIN as exactly four digits, reusing the existing rule rather
   than restating it;
5. create the `Profile` with `role=UserRole.player`, `is_active=True`,
   `failed_login_count=0`, `locked_until=None`;
6. reuse `_upsert_membership` for the league membership, with
   `LeagueMemberRole.player`;
7. write the same audit entry the authenticated route writes, and call
   `notify_member_joined`; and
8. issue and return a token pair via `_issue_token_pair`.

Notification preferences need no work here. `get_preferences` creates defaults
on first access, unlike the sibling application which inserts them at signup.

The profile model needs no new columns. `Profile` carries only
`display_name`, `pin_hash`, `role`, `timezone`, `is_active`,
`failed_login_count`, `locked_until`, and `deleted_at`, so the sibling
application's placeholder-email workaround is unnecessary.

### Rate limiting

The existing authenticated route uses `key_func=per_user_key`, which cannot
work without a user. Use a proxy-aware client-address key in the style of
`login_key` in `apps/api/src/rate_limit.py`, which already combines a body
field with `client_address(request)`. Key on code plus client address so one
address cannot grind through codes, and keep the limit at or below the
sibling application's 30/hour.

### Frontend

- Move the `/leagues/join` route out of `<ProtectedRoute>` in `App.tsx`, or add
  a second unauthenticated route that renders the same page in signup mode.
- `JoinByCodePage.tsx` currently attaches `Authorization: Bearer` from
  `@/lib/tokens`. In the unauthenticated mode it must omit that header, collect
  display name, PIN, and timezone, then persist the returned token pair through
  the same path login uses before navigating to the league.
- Surface the four failure cases distinctly: invalid code, league full, display
  name taken, malformed PIN.

### Administration

Expose the league's join code and the existing rotate action in the admin UI so
the owner can distribute and revoke it without the API. The backend route
already exists.

## Security considerations

- A six-character code drawn from hexadecimal is roughly 16.7 million
  combinations. Rate limiting is what makes that adequate, so the limiter is
  part of the feature, not a refinement.
- Anyone holding the code can create an account. Rotation is the revocation
  mechanism; it does not remove members who already joined.
- `max_members` is the backstop. The bootstrap sets it to at least 15; confirm
  it matches the intended league size before distributing the code.
- The endpoint accepts an unauthenticated write that creates a row, so it must
  be included in the next security review pass.

## Testing

- Successful signup creates exactly one profile and one membership, and returns
  a working token pair.
- Invalid code, full league, duplicate display name differing only by case, and
  a non-four-digit PIN are each rejected with the intended status.
- Two concurrent signups on the same display name produce one profile and one
  clean rejection.
- The new member can log in afterwards with the PIN they chose.
- A subsequent roster bootstrap that does not list the new member leaves that
  member's profile and PIN untouched.
- Rate limiting rejects beyond the configured ceiling and keys on client
  address, not on a user.

## Consequences

- L0's private-provisioning decision and the `seeds.py` docstring both become
  inaccurate and must be amended in the same change.
- L5's "send member invites" step becomes "distribute the join code".
- The roster bootstrap stays for the administrator, so L4's expected-count
  evidence is unaffected by this ADR.
- Members choose their own PINs at signup, so the PIN-reset-on-re-run problem
  disappears for everyone who arrives this way.

## Out of scope

Email, email verification, invite tokens, and public reset links. L1 removed
those surfaces deliberately and this ADR does not reintroduce them.
