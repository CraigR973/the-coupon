# Lens 01 — Security — progress

Resume from this file alone. Ports: API 8110, web 4310. Ids from SEC-27.
Stack: `~/.cache/the-coupon/ci-local-venv/bin/python /Users/craigrobinson/the-coupon/docs/review/2026-09-28/notes/harness/stack.py --name sec --api-port 8110 --origin http://127.0.0.1:4310 --seed`
(run in background; kill with SIGTERM when done). Save output as `.txt` (`*.log` is gitignored).

Interrupted once: usage limit 28 Sep ~23:04, resumed 29 Sep 08:40 (lead killed the old stack).

## State

| step | state | evidence |
| --- | --- | --- |
| briefs, prompt, prior 01-security, prior README read | done | — |
| router inventory + diff since 2ce6f42 | done | `routes.tsv` (84 API routes), `routes-2ce6f42.txt` vs `routes-main.txt`: 5 new routes (me/export, me/delete, me/rename-notice GET + seen, admin/picks/{id}/correct) |
| code read: deps, auth, rate_limit, me, account_erasure, rename_notice, admin diff, league_memberships, leagues (partial) | done | leads below |
| stack up | todo (restart) | |
| seed script (league B, outsider, site admins) | todo | `seed_matrix.py` |
| authz matrix probed | todo | |
| cross-league IDOR | todo | |
| SEC-15..26 re-driven | todo | |
| SEC-01..13 spot-check | todo | |
| new surfaces (136, 134, 135/148, 132, 123, 129, 141, 145) | todo | |
| OSV live query | todo | |
| secrets scan + redaction check | todo | |
| production headers + health | todo | |
| 01-security.md written | todo | |

## Leads from code reading (to verify on the stack)

1. **Per-source login backoff (Batch 123) does not gate anything.** `login()` increments and
   commits the victim's `failed_login_count` (and locks) *before* `charge_failure()` raises
   429. No pre-check of the source bucket. So one address can still lock any number of
   accounts; the 429 arrives after the damage. Test `test_one_source_cannot_work_a_leaderboard...`
   asserts only `refusals > 0`. Verify: 5 victims × 5 wrong PINs from one source → victims 4-5
   still locked (423 on correct PIN).
2. Lockout push: one per lock (locked_until reset on expiry) → sustained griefing sends 4/hour,
   tag `account-locked` collapses on device. Assess harassment.
3. **SEC-15 bypass via demote:** league admin X demotes co-admin Y (allowed when 2+ admins),
   then Y is no longer "admin of any league" → X resets Y's PIN → claims via unauthenticated
   `/auth/pin/set`. Verify.
4. `require_league_admin` (leagues.py:240) still has the site-admin bypass for every league-admin
   **write** (PATCH/DELETE league, promote/demote/remove, invites, reset-pin, rotate, join-request
   approve/reject, refresh rounds). Batch 125 scoped only the member dependency. Judge vs SEC-17.
5. `/me/delete` PIN check: 403 on wrong PIN, rate limit 5/hour in-memory per user; no lockout
   counter. Stolen access token + PIN guessing → irreversible delete. Assess.
6. Erased member keeps active memberships (by design for standings) — check capacity count,
   admin-role residue; re-registrant inheritance (things keyed by name: invites hint nulled,
   login buckets deleted, pin/set window).
7. `CreateLeagueInviteRequest.display_name_hint` and `UpdateLeagueRequest.description` have no
   max_length (column String(100) for hint → possible 500).
8. Audit scope uses `changes->>'league_slug'`; slugs are globally unique incl. deleted and
   immutable → no cross-league bleed (checked).
9. `/leagues/{slug}/join` on public_open: removed member can rejoin by slug (inherent to open).

## Exact next step

Start the stack, write `seed_matrix.py` (league B with Dave admin / Erin member, outsider Frank,
site admin Sam non-member, site admin Sadie member of A, Gary admin of B + member of A,
public_request league C, soft-deleted league D with invite), mint tokens with the harness
JWT secret, then run the matrix probe.
