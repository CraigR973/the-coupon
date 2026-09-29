# Lens 06 — premium design — progress

Resume from this file alone. Ports: API 8160, web 4360. New ids from DES-10.
Brief: `../briefs/common.md` + `../briefs/06-design.md`.

## How to (re)start (never `cd`)

```
~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/06-design/stack_design.py --name design --api-port 8160 --origin http://127.0.0.1:4360 --seed   # background
~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/06-design/build_web.py   # background; prod bundle, CSS must be ~45.8 KB
~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/06-design/seed_design.py --reset --login
```
- `stack_design.py` = harness stack.py serving `review_server:app` (e2e server + `POST /__review/move-price`, `GET /__review/books`) so price-moved is driven for real.
- `seed_design.py` = lens 03's seed + Hana, Ivan, Jo, Kai, Lee in the-coupon (to exhaust the 50/hour league pick budget for real). Sessions → `<scratchpad>/design-sessions.json`.
- `lib.mjs` = lens 03's helpers, ports changed. Node: `. ~/.nvm/nvm.sh && nvm use 24 --silent && node <script>.mjs`.
- Pick budget is in-memory: restart the stack with `--keep-data` (no `--seed`) to reset it.

## Done
- 23:36 read briefs, prompt, prior lens doc, INDEX.
- 23:50 stack (8160) + bundle (4360, CSS 45,794 B) up; seeded (seed-output.txt).

- 00:05 Part 2.3 feedback states driven for real, 24 captures, INDEX rows written (make_index.py from captures.json):
  confirmed / conflict (Bob races Alice) / price-moved (fake price moved) / busy (budget exhausted, busy.mjs) / queued-offline.
  FOUND: dark-mode toast title contrast 1.01-1.07:1 (index.css override from 4121cf0 + Sonner theme light) — live (prod CSS index-Br02Ny1y.css identical).
  FOUND: queued-offline shows NO toast/notice (React Query pauses the mutation offline; spinner only); on reconnect the pick lands (201).

## Plan / order
A. [done] open-round: feedback captures confirm / conflict / price-moved (real) / queued-offline; standalone safe-area; PWA manifest+icons.
B. [done, no restart needed] restart API --keep-data → exhaust budget with 5 members × 10 → Alice sees PICKS_BUSY.
C. lock + settle in process with a void leg → settled results, settled coupon, standings; erase a member → "Former" copy.
D. judge corpus (Part 1 + peripheral), write lens doc, top-ten + mockups + contrast numbers.

## In flight
- Phase C next: lock + settle with a void leg (in process), erase a member.
