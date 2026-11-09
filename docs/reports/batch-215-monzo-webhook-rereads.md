# Batch 215 — selective Monzo webhook re-read refusals

Checked 9 Nov 2026. API-only payments-service repair; production behaviour changes only
after the owner's separate `/ship-prod`. No migration, money movement, matching change
or production webhook registration change.

## Evidence

- Retained logs from payments deployment `d2ba459a-ecfe-483e-bb25-7ba55c0a6bc1` contain
  49 `400 bad_request.app_version_outdated` re-read refusals, one webhook `matched=1`
  and three webhook `duplicate=1` entries. The retained refusal timestamps span
  7 Nov 00:09–13:13 UTC. Logs contain no transaction-kind association, so cannot prove
  which kinds failed. The current deployment's returned log sample contains none.
- The owner approved one bounded read-only probe on 9 Nov: up to two open accounts,
  100 transactions each from the last seven days and six individual re-reads, maximum
  11 GETs; stop on refusal. It used six GETs and stopped at the first refusal. No token
  refresh, POST, registration change, ingestion or database write occurred. The token
  snapshot and league/pot references were read in a read-only database transaction.
- Two uncapped account pages contained 40 ordinary transactions, 11 league link payments,
  11 pot filings, one league pot top-up and one other pot top-up. Two ordinary individual
  reads returned 200 with the requested id. The first league-link individual read returned
  `400 bad_request.app_version_outdated`, although that exact id had just been listed.
  The probe then stopped. Pot-top-up individual reads and the other link-payment kinds
  were not probed; the result is selective evidence, not a universal transaction rule.
- [Monzo's developer reference](https://docs.monzo.com/#retrieve-transaction) documents
  the same individual GET with Bearer authentication and optional merchant expansion.
  Its [list endpoint](https://docs.monzo.com/#list-transactions) supports account, time
  and pagination arguments. The reference does not define `app_version_outdated` or
  document an app-version header. The exact internal Monzo reason remains unknown;
  the demonstrated defect is an individual-read limitation for a listed league payment.

## Mechanism and decisions

```text
Unsigned webhook: transaction id only
  ↓
Authenticated individual GET
  ├─ succeeds → existing parsing and matching
  └─ 400 app_version_outdated
       ↓
     Authenticated open accounts + recent list pages
       ↓
     Exact requested id found? → existing parsing and matching
       ↓ no
     Leave recovery to the unchanged five-minute read
```

- Keep useful webhooks. Disabling them is contradicted by the retained matched payment.
- Recover only the exact 400/code combination. No guessed app-version header, payload
  trust, new Monzo endpoint or generic fallback for other refusals.
- Search from the later of the counting start and one hour ago. Use the existing 100-row
  page size, transaction-id pagination and a cap of three list pages across all open
  accounts per attempt. A webhook normally uses one GET; one recovery attempt uses at most five GETs
  including the initial refusal and account discovery. The existing one-time 401 token
  refresh/retry can repeat the attempt, for at most ten GETs plus one refresh POST.
  Other listed rows are never ingested.
- Preserve the list account as the transaction's account provenance for top-up holder
  naming. Existing link, league, pot, timing, deduplication and payer-matching rules apply.
- Never advance `read_through` in the webhook path. A missing id, a busy feed exceeding
  the cap, an old event or a list outage remains recoverable by the five-minute read.

## Verification and limits

Eighteen added synthetic cases cover app/card link-payment recovery before a scheduled
read, exact-id filtering and forged payloads, duplicate events plus scheduled reads,
top-up account provenance, multiple leagues/accounts, other-link rejection, refusal
selection, successful individual reads, list outages, time floors, pagination, page caps,
repeated cursors, malformed pages and a 401 on the third list page followed by one
refresh/retry and successful recovery. Existing assertions remain unchanged.

The first clean-PostgreSQL payments module run passed all 108 then-present tests; Mypy
passed all 106 source files. Review then added the fallback-401 case, raising the module
to 109 tests. The complete gate and exact-SHA CI results belong in this batch's session-log entry.
The initial targeted lint check found one overlong new test signature; pinned Ruff
formatting fixed it. A local test-count inspection initially used an older system Python
without `ast.unparse`; rerunning with the pinned gate Python counted 17 added cases.
Review found the three-page bound needed qualifying as per attempt because the existing
401 retry restarts the lookup; the report and architecture were clarified and a regression
case added before the full gate.
The first scratch-PostgreSQL start failed before tests because the inherited locale was
invalid; the clean rerun explicitly used `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`.
Full gate attempt 1 passed 11 of 12 checks (including 1,418 frontend tests and the seeded
journey); its backend run had 1,649 passes and one failure:
`test_config.py::test_odds_api_is_the_default_provider`. The invocation had unnecessarily
exported `ODDS_PROVIDER=fake`, overriding the production-default setting that this test
checks. The same unchanged test passed alone with that override removed. The correction
is to run the canonical gate with `ODDS_PROVIDER` unset; no test, assertion or application
default was changed. The complete gate must pass again before close-out.

Synthetic evidence establishes the implementation contract. Production recovery still
needs the owner's shipment and a natural payment readback showing the recovery line and
the resulting single ledger entry. Do not manufacture that evidence with a payment,
manual refresh or unapproved bank probe. The batch does not deregister or re-register
the production webhook; any such change remains the owner's shipment decision.
