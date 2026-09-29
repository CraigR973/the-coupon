# Lens 02 — Correctness — progress

Ports: API 8120, web 4320. New ids from CORR-19. Stack name `corr`.
Command output is saved as `.txt` (`*.log` is gitignored).

## Done
- Read common brief, lens brief, 00-prompt, BUILD_PLAN contract + rows 95/115/120/121/130-136/147/156/157/159-161, 2026-09-13 02-correctness + README.

## In flight
- Reading the changed code since 2ce6f42 (picks router, calendar, scoring, completion, erasure, correction, settle notify, discovery budget, reminders, backup).

## Next step
- Start stack: `~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/harness/stack.py --name corr --api-port 8120 --origin http://127.0.0.1:4320 --seed` (background), then write `seed_two_leagues.py` in this dir.

## Prior findings status
| id | status | evidence file |
| --- | --- | --- |
