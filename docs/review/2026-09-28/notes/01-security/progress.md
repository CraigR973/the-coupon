# Lens 01 — Security — progress

Resume from this file alone. Ports: API 8110, web 4310. Ids from SEC-27.
Stack: `~/.cache/the-coupon/ci-local-venv/bin/python /Users/craigrobinson/the-coupon/docs/review/2026-09-28/notes/harness/stack.py --name sec --api-port 8110 --origin http://127.0.0.1:4310 --seed`
(background; SIGTERM when done). Then `seed_matrix.py` (writes scratchpad/matrix-actors.json with
minted tokens). Output as `.txt` (`*.log` is gitignored). Evidence transcript: `probes.txt`.

Interruptions: 28 Sep ~23:04 (usage), 29 Sep ~08:50 (usage). Resumed 14:17. Stack on 8110 was
still running with the seeded state below (league A has been mutated by the probes: hank demoted
and his PIN taken over; v1-v5 locked at 08:00 UTC, expired now; league A code rotated; erin
joined A; league A description edited by sam).

**Write findings into `../../01-security.md` as each one is verified.**

## State

| step | state | evidence |
| --- | --- | --- |
| router inventory + diff since 2ce6f42 | done | `routes.tsv` 84 routes; 5 new (me/export, me/delete, me/rename-notice ×2, admin/picks/{id}/correct) |
| matrix 73 routes × 7 roles | done | `matrix.txt`/`matrix.csv`; 3 "mismatches" are all expected (PIN-check 401/403 before auth-able work, site-admin self-delete 409, private-league join 403) |
| SEC-15 | partial — held for site admin + other-league admin; **bypass: demote co-admin then reset** (SEC-27) | probes.txt "SEC-15" sections |
| SEC-18 API half | **not fixed** — 5 victims locked from one source; victims 4-5 got 429 but were still locked (SEC-28) | probes.txt "SEC-18" |
| SEC-16 | held (code rotated on removal, old code 404; public_request by code → pending) | probes.txt |
| SEC-17 | held for member writes; league-admin writes keep site-admin bypass (PATCH, invite, rotate all 200 for non-member sam; audited as "Sam") → INFO/owner note | probes.txt |
| SEC-20 | held for exact/case/padding/reserved/charset; **but override may equal a non-member's global name, who can then join → two "Erin"s** (SEC-29, LOW-MED); confusables CaroI/Car0l accepted (same as registration) | probes.txt |
| SEC-23 port | held (8443, 22 refused; 443 ok). timeout: code-read todo |
| SEC-26 | held (404) |
| SEC-18 web half | todo: code read says refresh before PIN (AuthContext.tsx:118-140) — cite as code-held; optionally verify |
| SEC-19 CSP, SEC-21, SEC-22, SEC-25 | todo |
| SEC-01..13 spot-check | todo |
| 136 delete/export | done — held; written into doc (Checked) | probes.txt "136" |
| new surfaces 134, 135/148, 132, 129, 145 | todo | |
| OSV, secrets, prod headers | todo |
| 01-security.md | todo — start now |

## Leads still to check

- `/me/delete` PIN check has no lockout counter, 5/hour in-memory per user.
- Erased member keeps active memberships (capacity), re-registrant inheritance.
- `display_name_hint` (String(100)) and league `description` unbounded → possible 500 / bloat.
- Lockout push: one per lock; sustained griefing → 4/hour, tag collapses.

## Exact next step

Write 01-security.md skeleton with SEC-27/28/29 and the prior table so far; then 136 deletion
probes; then headers/OSV/secrets.
