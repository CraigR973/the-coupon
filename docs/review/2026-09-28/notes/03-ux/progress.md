# Lens 03 — UX / accessibility — progress

A fresh session resumes from this file alone. Brief: `../briefs/common.md` + `../briefs/03-ux.md`.
Ports: API 8130, web 4330. Stack name `ux`. New ids from UX-21.

## How to (re)start

```
~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/harness/stack.py --name ux --api-port 8130 --origin http://127.0.0.1:4330 --seed   # background
~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/03-ux/build_web.py   # background — NOT harness/web.sh (unstyled bundle)
~/.cache/the-coupon/ci-local-venv/bin/python docs/review/2026-09-28/notes/03-ux/seed_states.py --reset --login
```
`--reset` re-runs the e2e base seed then adds every state; `--login` writes
`<scratchpad>/ux-sessions.json` (Alice, Bob, Carol, Dave) for `lib.mjs` to inject.
Personas: Alice = site admin + league admin of `the-coupon` + member of `sunday-club`;
Bob = member of the-coupon, admin of sunday-club; Carol = member; Dave = no league;
Erin = pending join request. the-coupon round OPEN (locks +3 days); sunday-club round
LOCKED; the-coupon season 2025 archive (rounds 37, 38 settled). Settled current round is
produced by `POST /__e2e/settle` after picks + `POST /__e2e/lock` (phase B, destroys open state).

## State

| step | state | evidence |
| --- | --- | --- |
| briefs, prompt, 2026-09-13 lens doc + INDEX read | done 29 Sep 08:40 | |
| seeding script | done, verified by API reads 08:45 | `seed_states.py` |
| Playwright helpers | written | `lib.mjs` |
| interrupted by usage limit ~08:50; resumed 14:47 | | lead committed notes as 0e1265e (pre-rewrite hash) |
| stack + bundle restarted | done 14:50; interrupted again ~15:00, resumed 18:32 | |
| **harness bundle is unstyled** | found 18:40 | `web.sh` builds with the wrong cwd: Tailwind `content` globs are cwd-relative, CSS 9.1 KB vs gate 45.8 KB. Replaced by `build_web.py` (cwd=apps/web via Python). Tell the lead: lens 02's screenshots built with web.sh are likely unstyled |
| sweep.mjs smoke (5 runs) | done 18:36 | `axe/open-smoke*` — discard, taken against the unstyled bundle |
| axe sweep open phase | **done 19:20**: 318 runs + 12 re-driven (`open-fix`) + 14 re-runs (`open-rerun`, all reproduced) | `axe/open*/`, `sweep-open-console.txt` |
| corpus batch 1 + INDEX | committed 19:25 (345 rows; 8 dup groups are genuine error=loading / error=empty) | `make_index.py`, `duplicates.txt` |
| zoom, contrast, motion, reflow probes | done 19:40 | `probe-*.txt/json` |
| findings UX-21..27 | written into lens doc 19:50 | |
| targets probe, focus.mjs | running (chained bg job) | `probe-targets*.txt`, `focus/` |
| gate probe | done 19:05 | `probe-gate.txt`: install gate over /login has no landmark, page behind not inert; Tab lands only on covered login fields → UX-22 |
| early axe results | player-profile lost rows (opacity-60, PlayerProfilePage.tsx:160) 2.24-2.8:1 all 4 runs → UX-21 (re-run pending); install gate region×6 → UX-22 | |
| state captures + corpus | todo | `../../screenshots/` |
| keyboard pass | todo | |
| focus pixels (UX-14) | todo | |
| names, zoom, reflow, reduced motion, targets | todo | |
| repo a11y smoke coverage | done (read) | see below |
| lens doc | skeleton + method written 19:07 | `../../03-ux-accessibility.md` |

## Facts gathered so far

- Repo prod-bundle smoke (`apps/web/e2e/prod-bundle-*.spec.ts`, config
  `playwright.prod-bundle.config.ts`, Desktop Chrome 1280×720) is built against
  `https://api.example.invalid`, so it can reach only the 6 public routes.
  a11y spec: 6 public routes × 2 themes × 3 rules (`landmark-one-main`,
  `page-has-heading-one`, `region`) only. Reflow spec: same 6 routes at 320 px,
  no theme, clipping + page overflow. Nothing signed-in, nothing at 390, no
  colour-contrast, no focus-indicator check.
- Install gate (`InstallPromptController`) is UA-triggered (Android/iOS), not
  width-triggered: 390 captures use a desktop Chromium UA at 390×844 (the layout a
  standalone PWA gets). The gate itself is captured separately with a mobile UA.
- `AppToaster` only speaks toasts whose title is a string (all current call sites are).
- Cross-lens: lens 07 says UX-18 payout `opacity-60` is at `PickRow.tsx:238`, no batch.
- Lens 02 already added rows to `screenshots/INDEX.md` — append only.

## Findings so far (ids)

UX-21 player-profile lost row opacity (MED) · UX-22 install gate landmark + live form behind (MED) ·
UX-23 no h1 on profile loading/error (LOW) · UX-24 "Football Stats" tab wraps, icon 20×8 (LOW) ·
UX-25 error vs empty on 6 more screens incl. the coupon (MED) · UX-26 tab-bar indicator +156px (LOW) ·
UX-27 200% zoom header overflow 79px, account menu off-screen (LOW).
Prior: UX-13 held (5.08/5.6 + axe clean); UX-18 NOT fixed (2.40 light / 2.81 dark, disabled-button
caveat); reduced motion held (all animations 0 under reduce); UX-20 partial (chrome kept, 343/400 usable,
but UX-27); UX-15 partial (pick labels fine at 320; stat labels, standings h1, profile lines truncate).
UX-01 held (served viewport meta has no user-scalable/maximum-scale).

## Next step

After targets+focus finish: write their results; run `toasts.mjs` (Bob/Carol/Alice real picks +
mocked refusals), then `keyboard.mjs`; then Alice picks via API, `POST /__e2e/lock` →
`sweep --phase locked`; `POST /__e2e/settle` → `sweep --phase settled` (+ contrast of PickRow lost leg).
