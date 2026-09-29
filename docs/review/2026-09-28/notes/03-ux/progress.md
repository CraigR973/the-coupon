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
| axe sweep (every route × 2 themes × 390/1280) | todo | `axe/` |
| state captures + corpus | todo | `../../screenshots/` |
| keyboard pass | todo | |
| focus pixels (UX-14) | todo | |
| names, zoom, reflow, reduced motion, targets | todo | |
| repo a11y smoke coverage | done (read) | see below |
| lens doc | todo | `../../03-ux-accessibility.md` |

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

## Next step

Run `sweep.mjs --phase open` (all jobs, both widths, both themes) in the background,
writing to `axe/open/` and `axe/open-summary.tsv`; then phase `locked`/`settled`.
