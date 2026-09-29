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

- 23:50 Part 2.3 feedback states driven for real, 24 captures, INDEX rows written (make_index.py from captures.json):
  confirmed / conflict (Bob races Alice) / price-moved (fake price moved) / busy (budget exhausted, busy.mjs) / queued-offline.
  FOUND: dark-mode toast title contrast 1.01-1.07:1 (index.css override from 4121cf0 + Sonner theme light) — live (prod CSS index-Br02Ny1y.css identical).
  FOUND: queued-offline shows NO toast/notice (React Query pauses the mutation offline; spinner only); on reconnect the pick lands (201).

- 23:52 measure.mjs open phase (measure-open.txt): first price y=1134 at 390 (fold 783), y=856 at 1280 (fold 800); 0 nodes <12px; 19 tracked labels on the round.
- 23:56 Phase C done: settle_design.py (Alice/Hana picks, Kai erased, lock, in-process settle: 3 won/1 void/4 lost); settled.mjs 30 captures (settled-run.txt). 54 lens-06 INDEX rows.
  FOUND: settled slate still shows potential pts on lost/void selections; lost coupon headline is the price not the result; "TAKEN BY FORMER" (PickCard firstName); standings/results 2-col Z order at 1280 (8 members); stat labels truncate "PICKS …" at 390; home loading/error shows no-league copy.

- 00:00 PWA pass: pwa/icon-masks.html+png (maskable == icon-512 byte-identical; ticket ends outside 80% safe zone); pwa.mjs standalone+insets 59/34 (8 captures): header 140px, tab bar 95px, toast gap 15 (held), offline banner static (scrolls away). theme-color #071A3D (dark) vs header.
  FOUND: all 53 opacity-modified token utilities (126 uses, 40 files) compile to NOTHING (tokens are var() hex, no <alpha-value>) → header/tab bar have no fill (computed rgba(0,0,0,0)), no tints anywhere (opacity-modifier-audit.txt).

- 00:06 peripheral: opened ~30 lens-03 captures; 26 lens-03 captures carry a leaked offline banner (corpus-offline-banner-scan.txt), my-leagues--happy and league-members--happy are EMPTY → re-captured 9 screens as `*-l06--*` (peripheral.mjs). tabbar_probe.txt: indicator +156px always (absolute span in justify-around flex, no left-0), Football icon 20x8. cls.txt: round CLS 0.247 @390, standings 0.141, home 0.
  FOUND: Football Stats opens with every table collapsed; admin sub-nav labels overlap at 390; JoinPage names no league.

- 00:12 contrast.py → contrast.txt (110 pairs; naive tint enable fails 13 pairs — DES-11 fix must cap alphas). Lens doc 06-premium-design.md WRITTEN (Part 1, register DES-10..23, per screen, top ten, batches, decisions).

- 00:18 mockups built + shot (mockups/: toasts, round, standings, settled × 390 dark/light + 1280 dark = 12 PNGs); doc updated with mockup table.

- 00:20 all processes stopped (stack 8160, web 4360; no postgres left). Lens DONE.

## Plan / order
A. [done] open-round: feedback captures confirm / conflict / price-moved (real) / queued-offline; standalone safe-area; PWA manifest+icons.
B. [done, no restart needed] restart API --keep-data → exhaust budget with 5 members × 10 → Alice sees PICKS_BUSY.
C. [done] lock + settle in process with a void leg → settled results, settled coupon, standings; erase a member → "Former" copy.
D. judge corpus (Part 1 + peripheral), write lens doc, top-ten + mockups + contrast numbers.

## In flight (none)
- Lens 06 complete. Nothing in flight. If resumed: only follow-ups the lead asks for.
