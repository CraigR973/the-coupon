# Lens 01 — Security — progress

Resume from this file alone. Ports: API 8110, web 4310. Ids from SEC-27.
Stack: `~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/harness/stack.py --name sec --api-port 8110 --origin http://127.0.0.1:4310 --seed`
(run with absolute path, in background; kill with SIGTERM when done).

## State

| step | state | evidence |
| --- | --- | --- |
| briefs, prompt, prior 01-security, prior README read | done | — |
| router inventory + diff since 2ce6f42 | todo | |
| stack up | todo | |
| authz matrix probed | todo | |
| cross-league IDOR | todo | |
| SEC-15..26 re-driven | todo | |
| SEC-01..13 spot-check | todo | |
| new surfaces (136, 134, 135/148, 132, 123, 129, 141, 145) | todo | |
| OSV live query | todo | |
| secrets scan + redaction check | todo | |
| production headers + health | todo | |
| 01-security.md written | todo | |

## Exact next step

Inventory routers, start the stack.
