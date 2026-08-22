# ADR 0008 — Public self-serve registration

Status: **accepted and implemented**, 2026-08-22. Supersedes ADR 0001. The
problem ADR 0001 identified is the problem this solves; the mechanism is not the
one it proposed, and the difference is the substance of this record.

## Context

ADR 0001 was written on 2026-08-01, proposed and never implemented. It
established the finding that still holds: the product had **no account-creation
path at all** — not in the API, not in the UI. `routers/auth.py` exposed login,
refresh, logout, profile update, PIN change and PIN reset request, and nothing
else; `Profile` rows were constructed in exactly two places, both in `seeds.py`.

What that meant in practice was not discovered until the app was shared. Sending
someone the URL sends them to a sign-in form asking for a display name and PIN
they have never been given and cannot obtain. The invite link at `/join/:token`
was worse, not better: it recognised the token, then told the recipient to "sign
in with the display name and PIN provided by your admin". Every entry point into
the product dead-ended for everybody who was not already inside it.

ADR 0001's secondary finding also holds, and is confirmed in the code at
`seeds.py:172-178`: a roster bootstrap re-run rewrites `pin_hash` and clears
`failed_login_count` and `locked_until` for every roster entry it lists, so a
member who has chosen their own PIN silently loses it on an unrelated re-run.

## Decision

Add `POST /api/v1/auth/register` — unauthenticated, no invite, no join code, no
administrator in the loop. It creates a `Profile` and returns the same
`TokenResponse` login returns, so the caller lands signed in. Registration
creates an **account only**; it joins no league.

Recorded by the owner on 2026-08-22. This is a deliberate reversal of L0's
private-provisioning posture and is amended into `L0_PROJECT_IDENTITY.md` in the
same change, as ADR 0001 required.

### Why not ADR 0001's join-code gate

ADR 0001 proposed keying signup on the league's join code, mirroring the sibling
`wc_2026_predictor` application. That conflates two separate things:

- the join code gates **league membership**, and that gate already exists and
  works — `POST /api/v1/leagues/join-by-code`, with its capacity check,
  duplicate-membership check, audit and notification;
- an account is a **product-level identity**. The product is now per-league: a
  member may hold memberships in several leagues at once. Binding account
  creation to one league's code makes the second league a special case and
  leaves no way to hold an account while belonging to nothing.

It also double-gates the invite journey. A recipient of `/join/:token` already
holds a credential for the league; requiring a *league code* on top of an
*invite token* asks for two secrets to walk through one door.

Separating the two keeps each gate doing one job, and is why the web client
threads a `next` parameter through `/register` and `/login` — whichever door a
recipient picks, they return to the invite with the token intact.

### The cost, stated plainly

This model has no email and no phone number anywhere on `Profile`, and
`display_name` is both globally unique and the login identifier. Therefore:

- the first person to claim a name owns it across every league, permanently;
- there is no self-service account recovery. The only path is
  `pin/reset-request`, which writes an audit row and pushes every active site
  admin (Batch 56); and
- there is no verification step, so nothing proves a registrant is a person.

The following guards stand in for the verification this model does not have.
They are the feature, not refinements to it:

| Guard | Where | Why |
| --- | --- | --- |
| `REGISTER_LIMIT = "5/hour"`, keyed on the proxy-aware `client_address` | `routers/auth.py`, `rate_limit.py` | The only control between a public write endpoint and a scripted name-squatting run. Five an hour still lets a household sign up behind one NAT. |
| `PUBLIC_SIGNUP_ENABLED` | `config.py` | Closes registration without a deploy. With no email verification, a switch that needs a deploy is not a switch. |
| Case-insensitive uniqueness, **including soft-deleted rows** | `routers/auth.py` | Postgres would hold "Dave" and "dave" side by side; on a leaderboard they are one person twice. `deleted_at` does not release a name. |
| `IntegrityError` caught behind the pre-check | `routers/auth.py` | Two concurrent registrations pass the same check; the loser is told to pick another name rather than shown a 500. |
| Charset, length 2-32, whitespace collapsed | `routers/auth.py` | The name is typed back in at every sign-in, so anything unreproducible from a keyboard is a lockout waiting to happen. Must open with a letter or digit, so a name cannot be padded to sort first or made to look like UI chrome. |
| `is_weak_pin` | reused from Batch 58 | The PIN is the whole credential. |

Registration writes no `audit_log` row. `profiles.created_at` already records
that an account was made and when, and adding an `ActionType` value means
`ALTER TYPE ... ADD VALUE`, which cannot be undone against a production database
with no restore point (owner's 2026-07-30 deferral).

## Verification

Thirty-three backend test cases in `tests/test_auth.py` and seventeen frontend
tests in `test/RegisterPage.test.tsx`, all green in `scripts/ci-local.sh`,
covering:
successful creation and sign-in; the PIN stored hashed; whitespace collapsed
before both validation and storage; a taken name, a name differing only by case,
and a soft-deleted name each refused; the uniqueness race losing cleanly; weak
and malformed PINs refused; names outside the bounds and outside the charset
refused; the browser timezone kept, an unknown one refused, and UTC used when
absent; the kill switch refusing registration while leaving login undisturbed;
and the rate limit asserted against name-squatting rather than left in a
decorator string.

On the client: the post-registration redirect returns to the invite that sent
the member, falls back to the dashboard when nothing asked, and refuses to leave
the app for `//host`, `https://host` or `javascript:` — `next` is read straight
off a URL anyone can send, and a protocol-relative `//host` is a path to the
router but an absolute origin to the browser, so without that guard a shared
link could hand a member who has just authenticated to another host.

A 429 is surfaced as a rate limit rather than as a bad detail. The limiter answers
with `{ error: ... }` where the client reads `{ detail: ... }`, so without that
branch an honest household behind one NAT is told "could not create your account"
and invited to retry against a limit it has already spent.

Browser-verified end-to-end on 2026-08-22: an account created through the UI on
the desktop path and the mobile path, landing signed in.

## Consequences

- L0's private-provisioning decision is reversed and amended there.
- The `seeds.py` docstring is amended; the bootstrap is retained for the
  administrator and for recovery, and no longer describes the only way a profile
  is made.
- L5's "send member invites" becomes "share the link".
- Members who arrive this way choose their own PIN, so ADR 0001's
  PIN-reset-on-re-run problem does not reach them: they are not in the roster,
  so a bootstrap re-run does not touch them.
- The endpoint is an unauthenticated write that creates a row and must be
  included in the next security review pass. This carries forward from ADR 0001
  unchanged.
- `max_members` remains the per-league backstop. It does not bound account
  creation, which is what `PUBLIC_SIGNUP_ENABLED` and the rate limit are for.
- **A league whose `privacy` is `public_request` or `public_open` is discoverable
  and joinable without a code, and the population that can reach it just changed
  from "members the operator provisioned" to "anyone".** `the-coupon` is
  `private` and unaffected. The `test` league is `public_open` with its own
  135-fixture round, left in place by owner decision on 2026-08-20
  (`docs/runbooks/launch-readiness.md`) — that decision was taken while account
  creation was closed, and is worth revisiting now that it is not.

## Out of scope

Email, email verification, invite tokens beyond the existing `/join/:token`, and
public reset links. L1 removed those surfaces deliberately and this ADR, like
ADR 0001, does not reintroduce them.
