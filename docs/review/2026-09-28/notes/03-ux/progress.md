# Lens 03 — UX / accessibility — progress

A fresh session resumes from this file alone. Brief: `../briefs/common.md` + `../briefs/03-ux.md`.
Ports: API 8130, web 4330. Stack name `ux`. New ids from UX-21.

## State

| step | state | evidence |
| --- | --- | --- |
| briefs, prompt, 2026-09-13 lens doc + INDEX read | done 29 Sep 08:40 | |
| notes dir created | done | |
| stack + bundle up | todo | |
| seeding script (2nd league, settled, archive, locked, no-league member, site admin) | todo | `seed_states.py` |
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

## Next step

Start the stack (`stack.py --name ux --api-port 8130 --origin http://127.0.0.1:4330 --seed`)
and the bundle (`web.sh ux http://127.0.0.1:8130 4330`), both in the background.
